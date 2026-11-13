import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, time
from typing import Any

import httpx

from app.llm.custom_resolver import CustomDateTimeResolver
from app.llm.interfaces import DateTimeResolution

logger = logging.getLogger(__name__)

DEFAULT_EVON_TIMEOUT_SECONDS = 2.0


@dataclass
class EvonAnalysis:
    resolution: DateTimeResolution
    caller_name: str | None
    intent: str
    engine_used: str
    explanation: str


class EvonReasoningEngine:
    """Evon v3.3 Indic Reasoning Engine with fast deterministic guardrail fallback.

    Connects to a hosted Evon 30B MoE endpoint (or OpenAI/vLLM-compatible server)
    when EVON_API_BASE is set, and falls back seamlessly to the deterministic Indic
    rules engine if unconfigured, offline, or timed out.
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model_name: str = "evon-v3.3",
        timeout: float = DEFAULT_EVON_TIMEOUT_SECONDS,
    ) -> None:
        self.api_base = (
            api_base
            or os.environ.get("EVON_API_BASE", "").strip().rstrip("/")
            or ""
        )
        self.api_key = api_key or os.environ.get("EVON_API_KEY", "").strip()
        self.model_name = model_name
        self.timeout = timeout
        self.guardrail_resolver = CustomDateTimeResolver()
        self._cache: dict[tuple[str, str], EvonAnalysis] = {}
        self._max_cache_size = 128

    @property
    def is_live_configured(self) -> bool:
        return bool(self.api_base)

    def _should_call_llm(self, text: str, guardrail: EvonAnalysis) -> bool:
        if not self.is_live_configured:
            return False

        is_clean_date = (
            guardrail.resolution.date is not None
            and guardrail.resolution.time is not None
            and guardrail.resolution.confidence >= 0.90
        )
        is_clear_intent = guardrail.intent in (
            "confirm_booking",
            "retain_slot",
            "reject_or_reschedule",
            "query_saved_name",
            "query_identity_or_purpose",
        )

        text_lower = text.lower()
        has_idiom_or_filler = any(
            w in text_lower for w in ("ഓൾറെഡി", "പറഞ്ഞല്ലോ", "already", "പറഞ്ഞു")
        )
        has_name_cue = any(
            w in text_lower for w in ("പേര്", "പേരിൽ", "naam", "name", "മിസ്റ്റർ", "mr", "dr")
        )

        if has_idiom_or_filler or (has_name_cue and len(text.split()) > 3):
            return True

        if is_clean_date or is_clear_intent:
            return False

        return guardrail.resolution.confidence < 0.85

    async def reason(
        self,
        utterance: str,
        language: str = "ml-IN",
        context: dict[str, Any] | None = None,
    ) -> EvonAnalysis:
        """Analyze user utterance for Indic date/time, caller name, and conversational intent."""
        clean_text = utterance.strip()
        cache_key = (clean_text.lower(), language)
        if cache_key in self._cache:
            return self._cache[cache_key]

        guardrail = await self._fallback_deterministic(clean_text, language, context)
        needs_llm = self._should_call_llm(clean_text, guardrail)

        result = guardrail
        if needs_llm and self.is_live_configured:
            try:
                analysis = await self._call_evon_api(clean_text, language, context)
                if analysis is not None:
                    result = analysis
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Evon API call failed, falling back to deterministic guardrail: %s",
                    exc,
                )

        if len(self._cache) >= self._max_cache_size:
            first_key = next(iter(self._cache))
            self._cache.pop(first_key, None)
        self._cache[cache_key] = result
        return result

    async def resolve(
        self,
        text: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> DateTimeResolution:
        """Satisfies standard DateTimeResolver interface."""
        analysis = await self.reason(text, language, context)
        return analysis.resolution

    async def _call_evon_api(
        self,
        utterance: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> EvonAnalysis | None:
        url = f"{self.api_base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        system_prompt = (
            "You are Evon v3.3, a sovereign Indic reasoning model for medical appointment "
            "booking. Analyze user utterances in Indian languages (Malayalam, Hindi, Tamil, "
            "Telugu, Kannada, English, Hinglish, Manglish). Extract: "
            "1. Date (YYYY-MM-DD or null), 2. Time (HH:MM in 24hr format or null), "
            "3. Caller/Patient name (extract the actual person's name; NEVER use conversational "
            "fillers, idioms, or exasperation like 'ഓൾറെഡി പറഞ്ഞല്ലോ', 'മേംനെ പെഹ്‌ലെ ബോലാ' "
            "as a name), "
            "4. Intent: one of 'request_slot', 'provide_name', 'confirm_booking', "
            "'query_saved_name', 'retain_slot', 'reject_or_reschedule', 'other'. "
            "5. Confidence (0.0 to 1.0), 6. Brief explanation. "
            "Reply strictly with JSON object: {\"date\": ..., \"time\": ..., \"caller_name\": ..., "
            "\"intent\": ..., \"confidence\": ..., \"explanation\": ...}"
        )

        user_content = json.dumps(
            {
                "language": language,
                "utterance": utterance,
                "context": context or {},
            },
            ensure_ascii=False,
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "max_tokens": 200,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            return None

        content = choices[0].get("message", {}).get("content", "").strip()
        # Extract json object if wrapped in code blocks
        if "```" in content:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)

        parsed = json.loads(content)
        d_val: date | None = None
        t_val: time | None = None

        if parsed.get("date"):
            try:
                d_val = date.fromisoformat(str(parsed["date"]))
            except ValueError:
                d_val = None

        if parsed.get("time"):
            try:
                t_parts = [int(p) for p in str(parsed["time"]).split(":")[:2]]
                t_val = time(t_parts[0], t_parts[1])
            except (ValueError, IndexError):
                t_val = None

        confidence = float(parsed.get("confidence") or 0.95)
        explanation = str(parsed.get("explanation") or "Evon v3.3 Indic reasoning")
        caller_name = parsed.get("caller_name")
        if caller_name and isinstance(caller_name, str):
            caller_name = caller_name.strip()
            if len(caller_name) < 2 or caller_name.lower() in ("null", "none"):
                caller_name = None

        intent = str(parsed.get("intent") or "request_slot")

        resolution = DateTimeResolution(
            date=d_val,
            time=t_val,
            timezone="Asia/Kolkata",
            confidence=confidence,
            explanation=f"Evon v3.3: {explanation}",
        )

        return EvonAnalysis(
            resolution=resolution,
            caller_name=caller_name,
            intent=intent,
            engine_used="evon-v3.3",
            explanation=explanation,
        )

    async def _fallback_deterministic(
        self,
        utterance: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> EvonAnalysis:
        """Deterministic Indic guardrail for zero-latency local fallback."""
        resolution = await self.guardrail_resolver.resolve(
            utterance, language=language, context=context
        )

        # Name extraction via Indic postpositions and prefixes
        caller_name = self._extract_guardrail_name(utterance)

        # Intent detection
        intent = self._detect_guardrail_intent(utterance, resolution, caller_name)

        return EvonAnalysis(
            resolution=resolution,
            caller_name=caller_name,
            intent=intent,
            engine_used="evon-deterministic-guardrail",
            explanation=f"Guardrail ({resolution.explanation})",
        )

    def _extract_guardrail_name(self, text: str) -> str | None:
        name_chars = (
            r"A-Za-z"
            r"\u0900-\u097F"
            r"\u0980-\u09FF"
            r"\u0A00-\u0A7F"
            r"\u0A80-\u0AFF"
            r"\u0B80-\u0BFF"
            r"\u0C00-\u0C7F"
            r"\u0C80-\u0CFF"
            r"\u0D00-\u0D7F"
        )
        suffix_patterns = (
            rf"([{name_chars}\s]{{2,40}}?)\s+എന്ന\s+പേരി(?:ൽ|ലാ|ലാണ്|ൽത്തന്നെ)",
            rf"([{name_chars}\s]{{2,40}}?)\s+(?:के\s+नाम\s+से|ke\s+naam\s+se)",
            rf"([{name_chars}\s]{{2,40}}?)\s+(?:என்ற\s+பெயரில்|(?:enra|endra)\s+peyaril)",
        )
        for spat in suffix_patterns:
            smatch = re.search(spat, text, re.IGNORECASE)
            if smatch:
                raw_cand = smatch.group(1).strip()
                raw_cand = re.sub(
                    r"^(?:ഞാൻ|എന്റെ|എൻ്റെ|എന്‍റെ|ഇതിൽ|മേരാ|mera|my\s+name\s+is)\s+",
                    "",
                    raw_cand,
                    flags=re.IGNORECASE,
                ).strip()
                cand = self._clean_candidate(raw_cand)
                if cand and not self._is_disallowed(cand):
                    return cand

        prefixes = (
            r"(?:എന്റെ|എൻ്റെ|എന്‍റെ)\s+പേര്",
            r"പേര്",
            r"मेरा\s+नाम",
            r"naam\s+hai",
            r"mera\s+naam",
            r"name\s+is",
            r"I\s+am",
            r"this\s+is",
        )
        pattern = (
            rf"(?<![{name_chars}])(?:{'|'.join(prefixes)})(?![{name_chars}])"
            rf"\s*[:=]?\s*([{name_chars}\s]+)"
        )
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = match.group(1)
            cand = self._clean_candidate(raw)
            if cand and not self._is_disallowed(cand):
                return cand
        return None

    def _clean_candidate(self, raw: str) -> str | None:
        candidate = re.split(r"[.,\n;।॥!?]", raw.strip())[0].strip()
        candidate = re.sub(
            r"(?:\s+(?:അതിൽ|അതിൽത്തന്നെ|എന്ന്|എന്ന്\s+പറഞ്ഞ്|ബുക്ക്\s+ചെയ്തോളൂ|"
            r"ബുക്ക്\s+ചെയ്തോ|ബുക്ക്\s+ചെയ്യ്|ബുക്ക്\s+ചെയ്യുക|ബുക്ക്|"
            r"ബുക്കിംഗ്|book\s+it|book\s+karo|book|karo|please))+$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()
        candidate = re.sub(
            r"(?:\s+(?:hai|he|hun|hoon|aanu|anu|ആണ്|ആണു|ആണ്\s+എന്ന്|ആണ്\s+എന്ന്\s+പറഞ്ഞ്|"
            r"है|हूँ|हूं|आहे|হয়|ஆகும்|છે|ਹੈ))+$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()
        return candidate if len(candidate) >= 2 else None

    def _is_disallowed(self, text: str) -> bool:
        cleaned = text.strip().lower()
        if len(cleaned) < 2 or re.fullmatch(r"[\d\s\W]+", cleaned):
            return True
        tokens = set(re.findall(r"[\w\u0900-\u0D7F]+", cleaned))
        disallowed = {
            "ഓൾറെഡി", "പറഞ്ഞല്ലോ", "പറഞ്ഞു", "പറഞ്ഞില്ലേ", "നേരത്തെ",
            "ആയിക്കോട്ടെ", "അപ്പം", "അപ്പോ", "മതി", "ബുക്ക്", "ബുക്കിംഗ്",
            "എന്തിനാ", "എങ്ങനെ", "നോക്കട്ടെ", "ഇഷ്യൂ", "ഇഷ്യു", "ഇല്ല",
            "already", "said", "told", "earlier", "book", "booking",
        }
        if "ഓൾറെഡി" in tokens or "പറഞ്ഞല്ലോ" in tokens or "already" in tokens:
            return True
        return all(tok in disallowed for tok in tokens)

    def _detect_guardrail_intent(
        self,
        utterance: str,
        resolution: DateTimeResolution,
        caller_name: str | None,
    ) -> str:
        u_lower = utterance.lower()
        query_patterns = (
            r"പേര്\s*(?:ആയിട്ട്|ആയിട്ടാ|ആയിട്ടാണോ)?\s*എന്താ",
            r"പേരായിട്ട്\s*എന്താ",
            r"പേരായിട്ടെന്താ",
            r"പേരെന്താ",
            r"പേര്\s*പറയാമോ",
            r"പേര്\s*പറയാൻ\s*പറ്റുമോ",
            r"ഏത്\s*പേരിലാ",
            r"ഏത്\s*പേരിലാണ്",
            r"what(?:'s|\s+is)\s+(?:my\s+)?name",
            r"which\s+name",
            r"what\s+name",
        )
        if any(re.search(pat, u_lower) for pat in query_patterns):
            return "query_saved_name"
        identity_patterns = (
            r"ആരാണ്\s*(?:വിളിക്കുന്നത്|സംസാരിക്കുന്നത്|ഇത്)?",
            r"ആരാ\s*(?:വിളിക്കുന്നേ|സംസാരിക്കുന്നേ|വിളിച്ചേ|ഇത്)?",
            r"ആരാ\s+നീ",
            r"നിങ്ങൾ\s*ആരാണ്",
            r"ഹു\s*ഇസ്\s*കോളിംഗ്",
            r"hu\s*is\s*koling",
            r"who\s*(?:'s|\s+is)\s+(?:this|calling|speaking)",
            r"who\s+are\s+you",
            r"what\s+is\s+your\s+name",
            r"कौन\s*(?:बोल\s*रहा|है|हो)",
            r"आप\s*कौन\s*हैं",
            r"എന്തിനു\s*വേണ്ടി",
            r"എന്തിനുവേണ്ടി",
            r"എന്തിനാണ്",
            r"എന്തിനാ\s*വിളിച്ച(?:ത്|േ)",
            r"എന്താണ്\s*(?:ഈ\s*കോൾ|ഇത്|കേൾവി|വിഷയം|കാര്യം)",
            r"എന്താ\s*(?:ഇത്|വിഷയം|കാര്യം|സംഭവം)",
            r"മനസ്സിലായില്ല",
            r"എങ്ങനെ\s*(?:യൂസ്|ഉപയോഗിക്ക|ചെയ്യുക)",
            r"what\s+(?:is\s+this|is\s+this\s+for|is\s+this\s+call|can\s+you\s+do)",
            r"why\s+are\s+you\s+calling",
            r"what\s+do\s+you\s+do",
            r"how\s+(?:to\s+use|can\s+you\s+help)",
            r"किसलिए\s*(?:कॉल\s*किया|है)",
            r"क्या\s*(?:काम\s*है|मदद\s*कर\s*सकते|करते\s*हो)",
            r"समझ\s*नहीं\s*आया",
        )
        if any(re.search(pat, u_lower) for pat in identity_patterns):
            return "query_identity_or_purpose"
        if re.search(r"അപ്പോഴത്തേക്കിന്\s*ബുക്ക്|ഇഷ്യൂ\s*ഇല്ല|no\s+issue|no\s+problem", u_lower):
            return "retain_slot"
        if caller_name:
            return "provide_name"
        if resolution.date is not None or resolution.time is not None:
            return "request_slot"
        confirm_terms = (
            r"അതെ|ശരി|യെസ്|yes|okay|confirm|sure|ബുക്ക്\s+ചെയ്തോ|"
            r"ഉറപ്പാക്കിക്കോ|ഉറപ്പിച്ചോളൂ|ഉറപ്പിച്ചോ|ഉറപ്പാക്കാം|ഉറപ്പിക്കാം|ഉറപ്പാണ്|ഉറപ്പ്|"
            r"പുറപ്പാക്കിക്കോ|പുതപ്പാക്കിക്കോ|പാക്കിക്കോ|urapp"
        )
        if re.search(confirm_terms, u_lower):
            return "confirm_booking"
        if re.search(r"വേണ്ട|വേണ്ടാ|ഇല്ല|no|cancel|reject", u_lower):
            return "reject_or_reschedule"
        return "other"
