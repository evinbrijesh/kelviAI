const el = Object.fromEntries([
  'start', 'record', 'reset-demo', 'end', 'status', 'guidance', 'error', 'timer', 'stt', 'tts', 'llm',
  'state', 'empty', 'messages', 'playback', 'reply-audio', 'audio-note',
  'result', 'res-clinic', 'res-patient', 'res-time', 'res-ref',
  'detected-lang-badge', 'lang-switch-alert',
  'text-fallback', 'text-form', 'text-input', 'text-send',
  'toggle-xray', 'xray-panel', 'xray-badge', 'xray-lang', 'xray-resolved', 'xray-tool', 'xray-latency', 'xray-stack',
].map(id => [id, document.getElementById(id)]));

const languages = {
  'bn-IN': 'Bengali', 'en-IN': 'English', 'gu-IN': 'Gujarati', 'hi-IN': 'Hindi',
  'kn-IN': 'Kannada', 'ml-IN': 'Malayalam', 'mr-IN': 'Marathi', 'pa-IN': 'Punjabi',
  'ta-IN': 'Tamil', 'te-IN': 'Telugu',
};

const guidance = {
  awaiting_slot: 'Ask for an appointment date and time in Malayalam, Hindi, or English.',
  clarifying: 'Say the date and time again, specifying the hour.',
  awaiting_name: 'Provide a fictional patient name (e.g. Rahul Nair).',
  awaiting_confirmation: 'Review the proposed slot details, then say yes or no.',
  awaiting_cancellation: 'Provide your booking reference number to cancel.',
  awaiting_reschedule: 'Provide your booking reference and desired new time.',
  completed: 'Your appointment is confirmed. You can reset the demo to try another scenario.',
  failed: 'This call ended without booking. Start a new call or reset demo.',
  transferred: 'Call transferred to clinic staff. Reset demo to try again.',
};

const MAX_SECONDS = 12;
let mode = 'checking';
let callSid = null;
let stream = null;
let context = null;
let capture = null;
let source = null;
let chunks = [];
let sampleCount = 0;
let interval = null;
let deadline = null;
let audioUrl = null;
let generation = 0;
let audioEnded = null;
let previousLanguage = null;

function controls() {
  const isCallActive = Boolean(callSid);
  if (el.start) el.start.disabled = !['idle', 'done'].includes(mode) || isCallActive;
  if (el.record) {
    el.record.disabled = !['ready', 'recording'].includes(mode);
    el.record.textContent = mode === 'recording' ? '⏹ Stop & send turn' : 'Record your turn';
    if (mode === 'recording') el.record.classList.add('recording');
    else el.record.classList.remove('recording');
  }
  if (el['reset-demo']) el['reset-demo'].disabled = !isCallActive && ['idle'].includes(mode);
  if (el.end) el.end.disabled = !isCallActive || ['connecting', 'processing', 'ending'].includes(mode);
  if (el.timer) el.timer.hidden = mode !== 'recording';

  if (el['text-fallback']) {
    el['text-fallback'].hidden = !isCallActive || ['connecting', 'ending', 'done'].includes(mode);
    if (el['text-send']) el['text-send'].disabled = !['ready'].includes(mode);
    if (el['text-input']) el['text-input'].disabled = !['ready'].includes(mode);
  }
}

function setMode(next, statusText, instruction) {
  mode = next;
  if (el.status) el.status.textContent = statusText;
  if (instruction && el.guidance) el.guidance.textContent = instruction;
  controls();
}

function showError(error) {
  if (!el.error) return;
  el.error.textContent = error.message || 'The voice service encountered an error.';
  el.error.hidden = false;
}

function clearError() {
  if (!el.error) return;
  el.error.hidden = true;
  el.error.textContent = '';
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    if (!response.ok) {
      const messages = {
        404: 'This voice session has expired. Press Reset demo to start fresh.',
        413: 'The audio turn exceeds the 10MB limit. Try a shorter turn.',
        422: 'The audio could not be processed. Please try again.',
        429: 'The speech engine is busy. Please try again shortly.',
      };
      throw new Error(messages[response.status] || `Request failed with status ${response.status}.`);
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request timed out. Please check your connection.');
    if (error instanceof TypeError) throw new Error('Could not connect to the KelviAI service.');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function addMessage(speaker, text, langCode, transliteration) {
  if (el.empty) el.empty.hidden = true;
  if (!el.messages) return;

  const item = document.createElement('li');
  item.className = 'msg-item';
  item.dataset.speaker = speaker;

  const speakerLbl = document.createElement('span');
  speakerLbl.className = 'msg-speaker';
  speakerLbl.textContent = speaker === 'caller' ? 'You' : 'Assistant (KelviAI)';

  const utterance = document.createElement('p');
  utterance.className = 'msg-text';
  if (languages[langCode]) utterance.lang = langCode;
  utterance.textContent = text;

  item.append(speakerLbl, utterance);

  if (transliteration && transliteration.trim() !== text.trim()) {
    const translitEl = document.createElement('span');
    translitEl.className = 'translit-badge';
    translitEl.textContent = `🔤 ${transliteration}`;
    item.append(translitEl);
  }

  el.messages.append(item);
  item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function clearPlayback() {
  if (!el['reply-audio']) return;
  el['reply-audio'].pause();
  if (audioEnded) el['reply-audio'].removeEventListener('ended', audioEnded);
  audioEnded = null;
  el['reply-audio'].removeAttribute('src');
  el['reply-audio'].load();
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = null;
  if (el.playback) el.playback.hidden = true;
}

async function playReply(base64, instruction, terminal = false) {
  clearPlayback();
  if (!base64 || !el['reply-audio']) {
    setMode(terminal ? 'done' : 'ready', terminal ? 'Call complete' : 'Your turn', instruction);
    return;
  }
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
  audioUrl = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
  el['reply-audio'].src = audioUrl;
  if (el.playback) el.playback.hidden = false;
  if (el['audio-note']) el['audio-note'].hidden = true;

  const turnGen = generation;
  audioEnded = () => {
    if (turnGen === generation && mode === 'speaking') {
      setMode(terminal ? 'done' : 'ready', terminal ? 'Call complete' : 'Your turn', instruction);
    }
  };
  el['reply-audio'].addEventListener('ended', audioEnded, { once: true });
  setMode('speaking', 'KelviAI is speaking...', instruction);

  try {
    await el['reply-audio'].play();
  } catch {
    if (turnGen !== generation || mode !== 'speaking') return;
    if (el['audio-note']) {
      el['audio-note'].textContent = 'Autoplay was prevented. Click the player to listen, then record or type your reply.';
      el['audio-note'].hidden = false;
    }
    setMode(terminal ? 'done' : 'ready', terminal ? 'Call complete' : 'Your turn', instruction);
  }
}

export function encodeWav(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  writeText(0, 'RIFF');
  view.setUint32(4, buffer.byteLength - 8, true);
  writeText(8, 'WAVE');
  writeText(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 32768 : s * 32767, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

async function prepareWav(parts, count, rate) {
  const samples = new Float32Array(count);
  let offset = 0;
  for (const part of parts) {
    samples.set(part, offset);
    offset += part.length;
  }

  // Trim leading & trailing silence to minimize STT upload size and turn latency
  const SILENCE_THRESH = 0.008;
  let startIdx = 0;
  while (startIdx < samples.length && Math.abs(samples[startIdx]) < SILENCE_THRESH) {
    startIdx++;
  }
  const preRoll = Math.floor(rate * 0.15); // 150ms pre-roll to preserve plosives
  startIdx = Math.max(0, startIdx - preRoll);

  let endIdx = samples.length - 1;
  while (endIdx > startIdx && Math.abs(samples[endIdx]) < SILENCE_THRESH) {
    endIdx--;
  }
  const postRoll = Math.floor(rate * 0.15); // 150ms post-roll
  endIdx = Math.min(samples.length, endIdx + postRoll + 1);

  const trimmed = samples.subarray(startIdx, endIdx);
  const finalSamples = trimmed.length >= Math.floor(rate * 0.3) ? trimmed : samples;
  const finalCount = finalSamples.length;

  const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(finalCount * 16000 / rate)), 16000);
  const buffer = offline.createBuffer(1, finalCount, rate);
  buffer.copyToChannel(finalSamples, 0);
  const inp = offline.createBufferSource();
  inp.buffer = buffer;
  inp.connect(offline.destination);
  inp.start();
  const rendered = await offline.startRendering();
  return encodeWav(rendered.getChannelData(0));
}

function releaseMicrophone() {
  clearInterval(interval);
  clearTimeout(deadline);
  interval = null;
  deadline = null;
  if (capture) {
    capture.port.onmessage = null;
    capture.disconnect();
  }
  if (source) source.disconnect();
  capture = null;
  source = null;
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = null;
  if (context) void context.close().catch(() => {});
  context = null;
  chunks = [];
  sampleCount = 0;
}

async function recordTurn() {
  clearError();
  if (el['reply-audio']) el['reply-audio'].pause();
  const turnGen = generation;
  setMode('acquiring', 'Requesting microphone...', 'Please grant microphone access in your browser.');

  try {
    const obtained = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      video: false,
    });
    if (turnGen !== generation) {
      obtained.getTracks().forEach(t => t.stop());
      return;
    }
    stream = obtained;
    context = new AudioContext();
    const recCtx = context;
    await recCtx.resume();
    await recCtx.audioWorklet.addModule('/admin/static/voice-capture.js');
    if (turnGen !== generation) return;

    chunks = [];
    sampleCount = 0;
    let speechDetected = false;
    let silenceStart = null;
    let speechSamples = 0;
    const SILENCE_TIMEOUT_MS = 1100;
    const SPEECH_RMS_THRESHOLD = 0.012;

    capture = new AudioWorkletNode(recCtx, 'voice-capture');
    capture.port.onmessage = ({ data }) => {
      if (mode !== 'recording') return;
      const remaining = MAX_SECONDS * recCtx.sampleRate - sampleCount;
      if (remaining <= 0) return;
      const part = data.length > remaining ? data.slice(0, remaining) : data;
      chunks.push(part);
      sampleCount += part.length;

      // Energy check for voice activity
      let sum = 0;
      for (let i = 0; i < part.length; i++) sum += part[i] * part[i];
      const rms = Math.sqrt(sum / part.length);

      if (rms >= SPEECH_RMS_THRESHOLD) {
        speechDetected = true;
        silenceStart = null;
        speechSamples += part.length;
      } else if (speechDetected) {
        const now = performance.now();
        if (!silenceStart) {
          silenceStart = now;
        } else if (now - silenceStart >= SILENCE_TIMEOUT_MS && speechSamples >= recCtx.sampleRate * 0.4) {
          void sendTurn();
          return;
        }
      }

      if (sampleCount >= MAX_SECONDS * recCtx.sampleRate) void sendTurn();
    };
    source = recCtx.createMediaStreamSource(stream);
    source.connect(capture);
    capture.connect(recCtx.destination);

    stream.getAudioTracks()[0].addEventListener('ended', () => {
      if (mode === 'recording') {
        releaseMicrophone();
        setMode('ready', 'Microphone disconnected', 'Reconnect your microphone and record again.');
      }
    }, { once: true });

    setMode('recording', 'Listening...', 'Speak naturally — auto-sends when you pause, or click Stop & send turn.');
    const started = performance.now();
    const tick = () => {
      if (el.timer) {
        el.timer.textContent = `${Math.min(MAX_SECONDS, Math.floor((performance.now() - started) / 1000))} / ${MAX_SECONDS}s`;
      }
    };
    tick();
    interval = setInterval(tick, 250);
    deadline = setTimeout(() => {
      if (mode === 'recording') void sendTurn();
    }, MAX_SECONDS * 1000);
  } catch (error) {
    if (turnGen !== generation) return;
    releaseMicrophone();
    showError(new Error('Microphone unavailable or permission denied. You can still test seamlessly using the text box below.'));
    setMode('ready', 'Microphone unavailable', 'Use the text box below to type your request.');
  }
}

async function sendTurn() {
  if (mode !== 'recording') return;
  const parts = chunks, count = sampleCount, rate = context.sampleRate;
  setMode('processing', 'Processing voice turn...', 'Transcribing with Prisma, reasoning with Evon, and synthesizing with Timbre.');
  releaseMicrophone();

  if (count < rate * 0.2) {
    setMode('ready', 'Speech too short', 'Please record at least a short spoken phrase.');
    return;
  }
  try {
    const wav = await prepareWav(parts, count, rate);
    const turn = await request(`/api/voice/session/${encodeURIComponent(callSid)}/turn`, {
      method: 'POST',
      headers: { 'Content-Type': 'audio/wav' },
      body: wav,
    });
    await handleTurnResult(turn);
  } catch (error) {
    showError(error);
    setMode('ready', 'Turn stopped', 'You can retry or type your request below.');
  }
}

function updateXray(xray) {
  if (!xray || !el['xray-panel']) return;
  if (el['xray-badge']) el['xray-badge'].textContent = (xray.state || 'active').replaceAll('_', ' ');
  if (el['xray-lang']) {
    const langName = languages[xray.language] || xray.language || 'Indic';
    el['xray-lang'].textContent = `${langName} (${xray.language || 'auto'})`;
  }
  if (el['xray-resolved']) {
    if (xray.resolved_datetime && xray.resolved_datetime.date) {
      const res = xray.resolved_datetime;
      el['xray-resolved'].textContent = `${res.date} ${res.time || ''} (${Math.round((res.confidence || 0) * 100)}% conf)`;
    } else {
      el['xray-resolved'].textContent = 'No date/time extracted in turn';
    }
  }
  if (el['xray-tool']) {
    if (xray.tool_invoked) {
      const t = xray.tool_invoked;
      el['xray-tool'].textContent = `${t.name} → ${t.status || 'executed'}`;
    } else {
      el['xray-tool'].textContent = 'Direct dialogue response';
    }
  }
  if (el['xray-latency']) {
    const l = xray.latencies_ms || {};
    el['xray-latency'].textContent = `STT: ${l.stt_ms || 0}ms | Agent: ${l.agent_ms || 0}ms | TTS: ${l.tts_ms || 0}ms`;
  }
  if (el['xray-stack']) {
    if (xray.sovereign_stack) {
      const s = xray.sovereign_stack;
      el['xray-stack'].textContent = `${s.stt} → ${s.reasoning} → ${s.tts}`;
    } else {
      el['xray-stack'].textContent = 'Prisma v3.0 → Evon v3.3 → Timbre v2.5';
    }
  }
}

async function handleTurnResult(turn) {
  addMessage('caller', turn.caller_transcript || '(No speech detected)', turn.language, turn.caller_transliteration);
  addMessage('agent', turn.agent_reply, turn.language, turn.agent_transliteration);

  if (el.state) el.state.textContent = turn.state.replaceAll('_', ' ');

  // Update language badge and language switch alert
  const currentLangName = languages[turn.language] || turn.language || 'Auto';
  if (el['detected-lang-badge']) {
    el['detected-lang-badge'].textContent = `Lang: ${currentLangName}`;
  }

  if (previousLanguage && turn.language && previousLanguage !== turn.language) {
    const prevLangName = languages[previousLanguage] || previousLanguage;
    if (el['lang-switch-alert']) {
      el['lang-switch-alert'].textContent = `Language switch detected: ${prevLangName} → ${currentLangName}`;
      el['lang-switch-alert'].style.display = 'inline-block';
    }
  } else if (el['lang-switch-alert']) {
    el['lang-switch-alert'].style.display = 'none';
  }
  previousLanguage = turn.language;

  updateXray(turn.xray);

  // Booking Result Card
  if (turn.booking_id && el.result) {
    if (el['res-clinic']) el['res-clinic'].textContent = 'Nila Family Clinic (Synthetic)';
    if (el['res-ref']) el['res-ref'].textContent = `KLV-${turn.booking_id.padStart(4, '0')}`;
    if (turn.xray?.resolved_datetime) {
      const r = turn.xray.resolved_datetime;
      if (el['res-time']) el['res-time'].textContent = `${r.date} at ${r.time || '10:00 AM'}`;
    }
    // Extract patient name if in xray or text
    const patientName = turn.xray?.resolved_datetime?.caller_name || 'Rahul Nair';
    if (el['res-patient']) el['res-patient'].textContent = patientName;
    el.result.hidden = false;
  }

  await playReply(turn.audio_base64, guidance[turn.state] || 'Follow the instructions in the reply.', turn.is_terminal);
}

async function startDemoCall() {
  if (el.start && el.start.disabled) return;
  generation++;
  clearError();
  clearPlayback();
  previousLanguage = null;

  if (el.messages) el.messages.replaceChildren();
  if (el.empty) el.empty.hidden = false;
  if (el.result) el.result.hidden = true;
  if (el['lang-switch-alert']) el['lang-switch-alert'].style.display = 'none';

  setMode('connecting', 'Starting session...', 'Synthesizing sovereign opening greeting in Malayalam.');

  try {
    const start = await request('/api/voice/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel: 'browser_demo' }),
    });
    callSid = start.call_sid;
    previousLanguage = start.language;

    if (el['detected-lang-badge']) {
      el['detected-lang-badge'].textContent = `Lang: ${languages[start.language] || start.language}`;
    }
    if (el.state) el.state.textContent = start.state.replaceAll('_', ' ');

    addMessage('agent', start.greeting, start.language, start.transliteration);
    updateXray(start.xray);
    await playReply(start.audio_base64, guidance[start.state]);
  } catch (error) {
    showError(error);
    setMode(callSid ? 'uncertain' : 'idle', 'Call failed to start', 'Please check server connection and retry.');
  }
}

async function resetDemoSession() {
  generation++;
  releaseMicrophone();
  clearPlayback();
  clearError();

  if (callSid) {
    try {
      await fetch(`/api/voice/session/${encodeURIComponent(callSid)}/reset`, {
        method: 'POST',
        signal: AbortSignal.timeout(5000),
      });
    } catch {}
  }

  callSid = null;
  previousLanguage = null;
  if (el.messages) el.messages.replaceChildren();
  if (el.empty) el.empty.hidden = false;
  if (el.result) el.result.hidden = true;
  if (el['lang-switch-alert']) el['lang-switch-alert'].style.display = 'none';
  if (el.state) el.state.textContent = 'Idle';
  if (el['detected-lang-badge']) el['detected-lang-badge'].textContent = 'Lang: Auto';

  setMode('idle', 'Demo reset', 'Session cleared. Click Start demo or select a quick-start scenario.');
}

// Wire Event Listeners
if (el.start) el.start.addEventListener('click', startDemoCall);

if (el.record) {
  el.record.addEventListener('click', () => {
    if (mode === 'recording') void sendTurn();
    else if (mode === 'ready') void recordTurn();
  });
}

if (el['reset-demo']) el['reset-demo'].addEventListener('click', resetDemoSession);

if (el.end) {
  el.end.addEventListener('click', async () => {
    generation++;
    releaseMicrophone();
    clearPlayback();
    clearError();
    setMode('ending', 'Ending call...', 'Terminating active session.');
    try {
      if (callSid) {
        await fetch(`/api/voice/session/${encodeURIComponent(callSid)}/hangup`, {
          method: 'POST',
          signal: AbortSignal.timeout(5000),
        });
      }
    } catch {}
    callSid = null;
    if (el.state) el.state.textContent = 'Ended';
    setMode('done', 'Call ended', 'The conversation transcript remains above. Click Start demo to begin again.');
  });
}

if (el['toggle-xray'] && el['xray-panel']) {
  el['toggle-xray'].addEventListener('click', () => {
    const isHidden = el['xray-panel'].hidden;
    el['xray-panel'].hidden = !isHidden;
    el['toggle-xray'].setAttribute('aria-expanded', String(isHidden));
  });
}

// Text Fallback Form
if (el['text-form']) {
  el['text-form'].addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!callSid || mode !== 'ready') return;
    const text = el['text-input'].value.trim();
    if (!text) return;
    el['text-input'].value = '';
    setMode('processing', 'Processing request...', 'Analyzing utterance and synthesizing speech...');
    try {
      const turn = await request(`/api/voice/session/${encodeURIComponent(callSid)}/text-turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      await handleTurnResult(turn);
    } catch (error) {
      showError(error);
      setMode('ready', 'Request failed', 'You can retry or type another message.');
    }
  });
}

// Interactive Scenario Cards
document.querySelectorAll('.scenario-card').forEach(btn => {
  btn.addEventListener('click', async () => {
    const promptText = btn.dataset.prompt;
    if (!promptText) return;

    if (!callSid) {
      // Automatically start session first
      await startDemoCall();
      // Wait for session to be ready
      const waitForReady = setInterval(async () => {
        if (mode === 'ready' && callSid) {
          clearInterval(waitForReady);
          if (el['text-input']) el['text-input'].value = promptText;
          setMode('processing', 'Processing scenario...', 'Analyzing scenario prompt...');
          try {
            const turn = await request(`/api/voice/session/${encodeURIComponent(callSid)}/text-turn`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ text: promptText }),
            });
            await handleTurnResult(turn);
          } catch (err) {
            showError(err);
          }
        }
      }, 300);
    } else if (mode === 'ready') {
      if (el['text-input']) el['text-input'].value = promptText;
      setMode('processing', 'Processing scenario...', 'Analyzing scenario prompt...');
      try {
        const turn = await request(`/api/voice/session/${encodeURIComponent(callSid)}/text-turn`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: promptText }),
        });
        await handleTurnResult(turn);
      } catch (err) {
        showError(err);
      }
    }
  });
});

// Initialization
try {
  const status = await request('/api/voice/status');
  if (el.stt) el.stt.textContent = status.stt_model;
  if (el.tts) el.tts.textContent = status.tts_model;
  if (el.llm) el.llm.textContent = status.reasoning_model || 'Evon v3.3 (hybrid)';
  setMode('idle', 'Ready to start', 'Click Start demo or pick one of the quick-start test scenarios.');
} catch (error) {
  showError(error);
  setMode('unavailable', 'Service unavailable', 'Check server connectivity and reload this page.');
}
