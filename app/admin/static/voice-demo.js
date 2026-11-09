const el = Object.fromEntries([
  'start', 'record', 'end', 'status', 'guidance', 'error', 'timer', 'stt', 'tts',
  'language', 'state', 'empty', 'messages', 'playback', 'reply-audio', 'audio-note',
  'result', 'reference', 'dashboard', 'text-fallback', 'text-form', 'text-input',
  'text-send', 'alt-card', 'alt-text', 'toggle-xray', 'xray-panel', 'xray-badge',
  'xray-lang', 'xray-resolved', 'xray-tool', 'xray-latency',
].map(id => [id, document.getElementById(id)]));
const languages = { 'bn-IN': 'Bengali', 'en-IN': 'English', 'gu-IN': 'Gujarati', 'hi-IN': 'Hindi', 'kn-IN': 'Kannada', 'ml-IN': 'Malayalam', 'mr-IN': 'Marathi', 'pa-IN': 'Punjabi', 'ta-IN': 'Tamil', 'te-IN': 'Telugu' };
const guidance = {
  awaiting_slot: 'Ask for an appointment date and time.',
  clarifying: 'Say the date and time again, with a specific hour.',
  awaiting_name: 'Give a fictional name for this demo booking.',
  awaiting_confirmation: 'Check the date and time in the reply, then say yes or no.',
  awaiting_cancellation: 'Provide your booking reference number to cancel.',
  awaiting_reschedule: 'Provide your booking reference and desired new date/time.',
  completed: 'The booking action is saved. You can inspect it in the call dashboard.',
  failed: 'This call ended without a booking. Start a new call to try again.',
  transferred: 'The call has been handed off. Start a new call to try again.',
};
const MAX_SECONDS = 25;
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
const key = new URLSearchParams(location.search).get('api_key');
if (key) el.dashboard.href = `/admin/ui?${new URLSearchParams({ api_key: key })}`;

function controls() {
  el.start.disabled = !['idle', 'done'].includes(mode) || Boolean(callSid);
  el.record.disabled = !['ready', 'recording'].includes(mode);
  el.record.textContent = mode === 'recording' ? 'Send this turn' : 'Record your turn';
  el.end.disabled = !callSid || ['connecting', 'processing', 'ending'].includes(mode);
  el.timer.hidden = mode !== 'recording';
  if (el['text-fallback']) {
    el['text-fallback'].hidden = !Boolean(callSid) || ['connecting', 'ending', 'done'].includes(mode);
    if (el['text-send']) el['text-send'].disabled = !['ready'].includes(mode);
    if (el['text-input']) el['text-input'].disabled = !['ready'].includes(mode);
  }
}

function setMode(next, status, instruction) {
  mode = next;
  el.status.textContent = status;
  if (instruction) el.guidance.textContent = instruction;
  controls();
}

function showError(error) {
  el.error.textContent = error.message || 'The voice service could not complete this request.';
  el.error.hidden = false;
}

function clearError() { el.error.hidden = true; el.error.textContent = ''; }

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    if (!response.ok) {
      const messages = {
        404: 'This voice session has expired. End the call and start a new one.',
        413: 'The audio turn is too large. End the call and try a shorter turn.',
        422: 'The audio could not be read. End the call and try again.',
        429: 'The speech provider is busy. End the call and try again shortly.',
      };
      throw new Error(messages[response.status] || 'The voice request failed. Check the server configuration and Gnani access, then start a new call.');
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The voice request timed out. Its outcome may be unknown; end this call before trying again.');
    if (error instanceof TypeError) throw new Error('The server could not be reached. End this call before trying again; the last turn may already have been processed.');
    throw error;
  } finally { clearTimeout(timeout); }
}

function addMessage(speaker, text, language) {
  el.empty.hidden = true;
  const item = document.createElement('li');
  item.dataset.speaker = speaker;
  const label = document.createElement('span');
  label.className = 'speaker';
  label.textContent = speaker === 'caller' ? 'You' : 'KelviAI';
  const utterance = document.createElement('p');
  utterance.className = 'utterance';
  if (languages[language]) utterance.lang = language;
  utterance.textContent = text;
  item.append(label, utterance);
  el.messages.append(item);
}

function clearPlayback() {
  el['reply-audio'].pause();
  if (audioEnded) el['reply-audio'].removeEventListener('ended', audioEnded);
  audioEnded = null;
  el['reply-audio'].removeAttribute('src');
  el['reply-audio'].load();
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = null;
  el.playback.hidden = true;
}

async function playReply(base64, instruction, terminal = false) {
  clearPlayback();
  if (!base64) {
    setMode(terminal ? 'done' : 'ready', terminal ? 'Call complete' : 'Your turn', instruction);
    return;
  }
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
  audioUrl = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
  el['reply-audio'].src = audioUrl;
  el.playback.hidden = false;
  el['audio-note'].hidden = true;
  const turnGeneration = generation;
  audioEnded = () => {
    if (turnGeneration === generation && mode === 'speaking') {
      setMode(terminal ? 'done' : 'ready', terminal ? 'Call complete' : 'Your turn', instruction);
    }
  };
  el['reply-audio'].addEventListener('ended', audioEnded, { once: true });
  setMode('speaking', 'KelviAI is speaking', instruction);
  try { await el['reply-audio'].play(); }
  catch {
    if (turnGeneration !== generation || mode !== 'speaking') return;
    el['audio-note'].textContent = 'Automatic playback was unavailable. Press play to hear the reply before recording.';
    el['audio-note'].hidden = false;
    setMode(terminal ? 'done' : 'ready', terminal ? 'Call complete' : 'Your turn', instruction);
  }
}

export function encodeWav(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset, text) => { for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i)); };
  writeText(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true);
  writeText(8, 'WAVE'); writeText(12, 'fmt '); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  writeText(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

async function prepareWav(parts, count, rate) {
  const samples = new Float32Array(count);
  let offset = 0;
  for (const part of parts) { samples.set(part, offset); offset += part.length; }
  const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(count * 16000 / rate)), 16000);
  const buffer = offline.createBuffer(1, count, rate);
  buffer.copyToChannel(samples, 0);
  const input = offline.createBufferSource();
  input.buffer = buffer;
  input.connect(offline.destination);
  input.start();
  const rendered = await offline.startRendering();
  return encodeWav(rendered.getChannelData(0));
}

function releaseMicrophone() {
  clearInterval(interval); clearTimeout(deadline);
  interval = null; deadline = null;
  if (capture) { capture.port.onmessage = null; capture.disconnect(); }
  if (source) source.disconnect();
  capture = null; source = null;
  if (stream) stream.getTracks().forEach(track => track.stop());
  stream = null;
  if (context) void context.close().catch(() => {});
  context = null;
  chunks = []; sampleCount = 0;
}

async function recordTurn() {
  clearError();
  el['reply-audio'].pause();
  const turnGeneration = generation;
  setMode('acquiring', 'Requesting microphone access', 'Allow microphone access in your browser.');
  try {
    const obtained = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
    if (turnGeneration !== generation) { obtained.getTracks().forEach(track => track.stop()); return; }
    stream = obtained;
    context = new AudioContext();
    const recordingContext = context;
    await recordingContext.resume();
    await recordingContext.audioWorklet.addModule('/admin/static/voice-capture.js');
    if (turnGeneration !== generation) return;
    chunks = []; sampleCount = 0;
    capture = new AudioWorkletNode(recordingContext, 'voice-capture');
    capture.port.onmessage = ({ data }) => {
      if (mode !== 'recording') return;
      const remaining = MAX_SECONDS * recordingContext.sampleRate - sampleCount;
      if (remaining <= 0) return;
      const part = data.length > remaining ? data.slice(0, remaining) : data;
      chunks.push(part); sampleCount += part.length;
      if (sampleCount >= MAX_SECONDS * recordingContext.sampleRate) void sendTurn();
    };
    source = recordingContext.createMediaStreamSource(stream);
    source.connect(capture);
    capture.connect(recordingContext.destination);
    stream.getAudioTracks()[0].addEventListener('ended', () => {
      if (mode === 'recording') { releaseMicrophone(); setMode('ready', 'Microphone disconnected', 'Reconnect your microphone and record again.'); }
    }, { once: true });
    setMode('recording', 'Listening to your turn', 'Speak, then press Send this turn. Press End call to discard the audio.');
    const started = performance.now();
    const tick = () => { el.timer.textContent = `${Math.min(MAX_SECONDS, Math.floor((performance.now() - started) / 1000))} / ${MAX_SECONDS} seconds`; };
    tick(); interval = setInterval(tick, 250);
    deadline = setTimeout(() => { if (mode === 'recording') void sendTurn(); }, MAX_SECONDS * 1000);
  } catch (error) {
    if (turnGeneration !== generation) return;
    releaseMicrophone();
    const messages = {
      NotAllowedError: 'Microphone permission was denied. Allow it in the browser settings and record again.',
      NotFoundError: 'No microphone was found. Connect one and record again.',
      NotReadableError: 'The microphone is unavailable. Close other apps using it and record again.',
    };
    showError(new Error(messages[error.name] || 'Microphone capture is unavailable. Use a current browser on localhost or HTTPS.'));
    setMode('ready', 'Microphone unavailable', 'No audio was sent. You can record again or end the call.');
  }
}

async function sendTurn() {
  if (mode !== 'recording') return;
  const parts = chunks, count = sampleCount, rate = context.sampleRate;
  setMode('processing', 'Processing your voice', 'Gnani transcribes the audio, the agent handles the request, then Gnani speaks the reply.');
  releaseMicrophone();
  if (count < rate * .2) {
    setMode('ready', 'That turn was too short', 'Record at least a brief spoken request. No audio was sent.');
    return;
  }
  try {
    const wav = await prepareWav(parts, count, rate);
    const turn = await request(`/api/voice/session/${encodeURIComponent(callSid)}/turn`, { method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wav });
    await handleTurnResult(turn);
  } catch (error) {
    showError(error);
    setMode('uncertain', 'Voice request stopped', 'The turn may have been processed. End this call before starting another; do not resend a confirmation.');
  }
}

function updateXray(xray) {
  if (!xray || !el['xray-panel']) return;
  if (el['xray-badge']) {
    el['xray-badge'].textContent = (xray.state || 'active').replaceAll('_', ' ');
  }
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
      el['xray-tool'].textContent = `${t.name} -> ${t.status || 'executed'}`;
    } else {
      el['xray-tool'].textContent = 'Direct dialogue response';
    }
  }
  if (el['xray-latency']) {
    const l = xray.latencies_ms || {};
    el['xray-latency'].textContent = `STT: ${l.stt_ms || 0}ms | Agent: ${l.agent_ms || 0}ms | TTS: ${l.tts_ms || 0}ms`;
  }
}

if (el['toggle-xray'] && el['xray-panel']) {
  el['toggle-xray'].addEventListener('click', () => {
    const isHidden = el['xray-panel'].hidden;
    el['xray-panel'].hidden = !isHidden;
    el['toggle-xray'].setAttribute('aria-expanded', String(isHidden));
  });
}

async function handleTurnResult(turn) {
  addMessage('caller', turn.caller_transcript || '(No speech detected)', turn.language);
  addMessage('agent', turn.agent_reply, turn.language);
  el.language.textContent = languages[turn.language] || turn.language;
  el.state.textContent = turn.state.replaceAll('_', ' ');
  updateXray(turn.xray);

  // Detect alternative slot suggestions in the reply
  if (el['alt-card'] && el['alt-text']) {
    if (turn.state === 'awaiting_name' || turn.state === 'awaiting_confirmation') {
      const lower = turn.agent_reply.toLowerCase();
      if (lower.includes('nearest') || lower.includes('taken') || lower.includes('ലഭ്യമല്ല') || lower.includes('ലഭ്യമായ സമയം')) {
        el['alt-text'].textContent = turn.agent_reply;
        el['alt-card'].hidden = false;
      } else {
        el['alt-card'].hidden = true;
      }
    } else {
      el['alt-card'].hidden = true;
    }
  }

  if (turn.booking_id) {
    el.reference.textContent = `Booking reference ${turn.booking_id}. See the confirmed date and time in the reply below.`;
    el.result.hidden = false;
  }
  if (turn.is_terminal) {
    const sid = callSid;
    try { await request(`/api/voice/session/${encodeURIComponent(sid)}/hangup`, { method: 'POST' }); callSid = null; }
    catch { showError(new Error('The call concluded, but session cleanup failed. Press End call before starting another.')); }
  }
  await playReply(turn.audio_base64, guidance[turn.state] || 'Follow the instructions in the reply.', turn.is_terminal);
}

if (el['text-form']) {
  el['text-form'].addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!callSid || mode !== 'ready') return;
    const text = el['text-input'].value.trim();
    if (!text) return;
    el['text-input'].value = '';
    setMode('processing', 'Processing your request', 'Handling your input and synthesizing speech reply...');
    try {
      const turn = await request(`/api/voice/session/${encodeURIComponent(callSid)}/text-turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      await handleTurnResult(turn);
    } catch (error) {
      showError(error);
      setMode('uncertain', 'Request stopped', 'The turn may have been processed. End this call before starting another.');
    }
  });
}

el.start.addEventListener('click', async () => {
  if (el.start.disabled) return;
  generation++;
  clearError(); clearPlayback();
  el.messages.replaceChildren(); el.empty.hidden = false; el.result.hidden = true;
  if (el['alt-card']) el['alt-card'].hidden = true;
  setMode('connecting', 'Starting your call', 'Gnani is synthesizing the opening greeting.');
  try {
    const start = await request('/api/voice/session/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel: 'browser_demo' }) });
    callSid = start.call_sid;
    el.language.textContent = languages[start.language] || start.language;
    el.state.textContent = start.state.replaceAll('_', ' ');
    addMessage('agent', start.greeting, start.language);
    updateXray(start.xray);
    await playReply(start.audio_base64, guidance[start.state]);
  } catch (error) {
    showError(error);
    setMode(callSid ? 'uncertain' : 'idle', 'Call could not start', 'Check the server and speech provider configuration before trying again.');
  }
});
el.record.addEventListener('click', () => { if (mode === 'recording') void sendTurn(); else if (mode === 'ready') void recordTurn(); });
el['reply-audio'].addEventListener('error', () => {
  if (mode !== 'speaking') return;
  el['audio-note'].textContent = 'The spoken reply could not be played. Read the transcript and continue your turn.';
  el['audio-note'].hidden = false;
  setMode(callSid ? 'ready' : 'done', callSid ? 'Your turn' : 'Call complete');
});
el.end.addEventListener('click', async () => {
  generation++;
  releaseMicrophone(); clearPlayback(); clearError();
  setMode('ending', 'Ending your call', 'Discarding any unsent microphone audio.');
  try {
    const response = await fetch(`/api/voice/session/${encodeURIComponent(callSid)}/hangup`, { method: 'POST', signal: AbortSignal.timeout(10000) });
    if (!response.ok && response.status !== 404) throw new Error('The session could not be ended. Press End call to retry.');
    callSid = null;
    el.state.textContent = 'Ended';
    setMode('done', 'Call ended', 'Your transcript remains here. Start another call to begin a new conversation.');
  } catch (error) { showError(error); setMode('uncertain', 'Session cleanup failed', 'Press End call to retry before starting another call.'); }
});
window.addEventListener('pagehide', () => {
  generation++;
  releaseMicrophone(); clearPlayback();
  if (callSid) void fetch(`/api/voice/session/${encodeURIComponent(callSid)}/hangup`, { method: 'POST', keepalive: true }).catch(() => {});
});

try {
  const status = await request('/api/voice/status');
  el.stt.textContent = status.stt_model;
  el.tts.textContent = status.tts_model;
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
    throw new Error('This demo needs microphone capture and AudioWorklet support. Open it in a current browser on localhost or HTTPS.');
  }
  if (status.provider !== 'gnani') throw new Error('The demo requires the Gnani speech adapters. Check the model provider configuration.');
  setMode('idle', 'Ready for a voice call', 'Start the call, listen to the greeting, then record your request.');
} catch (error) { showError(error); setMode('unavailable', 'Voice demo unavailable', 'Check the server and browser requirements, then reload this page.'); }
