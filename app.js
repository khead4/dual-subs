const languageOptions = [
  { code: "ja", label: "Japanese" },
  { code: "en", label: "English" },
  { code: "zh-Hans", label: "Chinese (Simplified)" },
  { code: "zh-Hant", label: "Chinese (Traditional)" },
  { code: "ko", label: "Korean" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "pt-BR", label: "Portuguese (Brazil)" },
  { code: "ar", label: "Arabic" },
  { code: "hi", label: "Hindi" }
];

const sampleSubtitleCopy = {
  en: "If we miss this train, we will not see the lights in time.",
  "zh-Hans": "\u5982\u679c\u9519\u8fc7\u8fd9\u73ed\u5217\u8f66\uff0c\u6211\u4eec\u5c31\u6765\u4e0d\u53ca\u770b\u5230\u90a3\u4e9b\u706f\u4e86\u3002",
  "zh-Hant": "\u5982\u679c\u932f\u904e\u9019\u73ed\u5217\u8eca\uff0c\u6211\u5011\u5c31\u4f86\u4e0d\u53ca\u770b\u5230\u90a3\u4e9b\u71c8\u4e86\u3002",
  ja: "\u3053\u306e\u96fb\u8eca\u3092\u9003\u3057\u305f\u3089\u3001\u3042\u306e\u706f\u308a\u306b\u306f\u9593\u306b\u5408\u308f\u306a\u3044\u3002",
  ko: "\uc774 \uc5f4\ucc28\ub97c \ub193\uce58\uba74 \ubd88\ube5b\uc744 \uc81c\uc2dc\uac04\uc5d0 \ubcf4\uc9c0 \ubabb\ud574\uc694.",
  es: "Si perdemos este tren, no veremos las luces a tiempo.",
  fr: "Si nous ratons ce train, nous n'arriverons pas \u00e0 temps pour voir les lumi\u00e8res.",
  de: "Wenn wir diesen Zug verpassen, sehen wir die Lichter nicht mehr rechtzeitig.",
  it: "Se perdiamo questo treno, non vedremo le luci in tempo.",
  "pt-BR": "Se perdermos este trem, n\u00e3o veremos as luzes a tempo.",
  ar: "\u0625\u0630\u0627 \u0641\u0627\u062a\u0646\u0627 \u0647\u0630\u0627 \u0627\u0644\u0642\u0637\u0627\u0631 \u0641\u0644\u0646 \u0646\u0631\u0649 \u0627\u0644\u0623\u0636\u0648\u0627\u0621 \u0641\u064a \u0627\u0644\u0648\u0642\u062a \u0627\u0644\u0645\u0646\u0627\u0633\u0628.",
  hi: "\u0905\u0917\u0930 \u0939\u092e \u092f\u0939 \u091f\u094d\u0930\u0947\u0928 \u091a\u0942\u0915 \u0917\u090f, \u0924\u094b \u0939\u092e \u0930\u094b\u0936\u0928\u0940 \u0938\u092e\u092f \u092a\u0930 \u0928\u0939\u0940\u0902 \u0926\u0947\u0916 \u092a\u093e\u090f\u0902\u0917\u0947\u0964"
};

const nativeLanguageSelect = document.getElementById("nativeLanguage");
const targetLanguageASelect = document.getElementById("targetLanguageA");
const targetLanguageBSelect = document.getElementById("targetLanguageB");
const languageSummary = document.getElementById("languageSummary");
const trackA = document.getElementById("trackA");
const trackB = document.getElementById("trackB");
const subtitleStage = document.getElementById("subtitleStage");
const resultVideo = document.getElementById("resultVideo");
const safeAreaInput = document.getElementById("safeArea");
const trackGapInput = document.getElementById("trackGap");
const maxCharsInput = document.getElementById("maxChars");
const safeAreaValue = document.getElementById("safeAreaValue");
const trackGapValue = document.getElementById("trackGapValue");
const maxCharsValue = document.getElementById("maxCharsValue");
const themeSelect = document.getElementById("themeSelect");
const timingPreview = document.getElementById("timingPreview");
const sourceCards = document.querySelectorAll("[data-source-card]");
const mediaFileInput = document.getElementById("mediaFile");
const subtitleFileInput = document.getElementById("subtitleFile");
const sourceUrlInput = document.getElementById("sourceUrl");
const providerSelect = document.getElementById("providerSelect");
const outputModeSelect = document.getElementById("outputMode");
const payloadPreview = document.getElementById("payloadPreview");
const generatePayloadButton = document.getElementById("generatePayload");
const submitJobButton = document.getElementById("submitJob");
const watchNowButton = document.getElementById("watchNowButton");
const downloadLanguageAButton = document.getElementById("downloadLanguageAButton");
const downloadLanguageBButton = document.getElementById("downloadLanguageBButton");
const downloadVideoButton = document.getElementById("downloadVideoButton");
const simulateProcessingButton = document.getElementById("simulateProcessing");
const processSummary = document.getElementById("processSummary");
const statusList = document.getElementById("statusList");
const jobStatusBadge = document.getElementById("jobStatusBadge");
const jobStatusText = document.getElementById("jobStatusText");
const jobMessages = document.getElementById("jobMessages");
const artifactList = document.getElementById("artifactList");
const cueList = document.getElementById("cueList");
const playerHint = document.getElementById("playerHint");
const playerLabel = document.getElementById("playerLabel");
const progressCard = document.getElementById("progressCard");
const progressLabel = document.getElementById("progressLabel");
const progressPercent = document.getElementById("progressPercent");
const progressEta = document.getElementById("progressEta");
const progressMeta = document.getElementById("progressMeta");
const progressFill = document.getElementById("progressFill");

let currentJob = null;
let resultVideoUrl = null;
let generationProgressTimer = null;
let activeJobId = null;
let subtitleGenerationReady = true;
let subtitleGenerationReason = "";

const LOCAL_API_BASE = "http://127.0.0.1:8000";
const API_BASE_STORAGE_KEY = "dualSubtitleApiBase";

function normalizeApiBase(value) {
  const rawValue = String(value ?? "").trim();
  if (!rawValue) {
    return "";
  }

  try {
    const url = new URL(rawValue);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "";
    }
    url.hash = "";
    url.search = "";
    return url.toString().replace(/\/+$/, "").replace(/\/api$/i, "");
  } catch (error) {
    return "";
  }
}

function readStoredApiBase() {
  try {
    return normalizeApiBase(window.localStorage.getItem(API_BASE_STORAGE_KEY));
  } catch (error) {
    return "";
  }
}

function writeStoredApiBase(value) {
  try {
    window.localStorage.setItem(API_BASE_STORAGE_KEY, value);
  } catch (error) {
  }
}

function getQueryApiBase() {
  const params = new URLSearchParams(window.location.search);
  const queryValue = params.get("api") || params.get("apiBase");
  const apiBase = normalizeApiBase(queryValue);
  if (apiBase) {
    writeStoredApiBase(apiBase);
  }
  return apiBase;
}

function getConfiguredApiBase() {
  return (
    getQueryApiBase() ||
    normalizeApiBase(window.DUAL_SUBTITLE_API_BASE) ||
    readStoredApiBase()
  );
}

function getApiBase() {
  const configuredApiBase = getConfiguredApiBase();
  if (configuredApiBase) {
    return configuredApiBase;
  }

  if (window.location.protocol === "file:") {
    return LOCAL_API_BASE;
  }
  return "";
}

function getApiHostLabel() {
  const apiBase = getApiBase();
  if (!apiBase) {
    return "the hosted API";
  }
  if (apiBase === LOCAL_API_BASE) {
    return "the local API";
  }
  return `the hosted API at ${apiBase}`;
}

function isLocalHostname(hostname) {
  return ["localhost", "127.0.0.1", "0.0.0.0", "::1"].includes(hostname);
}

function isUsingLocalApi() {
  return getApiBase() === LOCAL_API_BASE || (!getConfiguredApiBase() && isLocalHostname(window.location.hostname));
}

async function redirectFromFileModeIfPossible() {
  if (window.location.protocol !== "file:" || getConfiguredApiBase()) {
    return false;
  }

  try {
    const response = await fetch(`${LOCAL_API_BASE}/api/health`);
    if (response.ok) {
      window.location.replace(LOCAL_API_BASE);
      return true;
    }
  } catch (error) {
  }

  return false;
}

function populateLanguageSelect(select, defaultCode) {
  languageOptions.forEach((option) => {
    const element = document.createElement("option");
    element.value = option.code;
    element.textContent = option.label;
    if (option.code === defaultCode) {
      element.selected = true;
    }
    select.appendChild(element);
  });
}

function getLabelForCode(code) {
  return languageOptions.find((option) => option.code === code)?.label ?? code;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function containsDenseScript(text) {
  return /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]/.test(text);
}

function subtitleWrapWidth(text, maxChars) {
  if (containsDenseScript(text) && !text.includes(" ")) {
    return Math.max(10, Math.floor(maxChars * 0.72));
  }
  return Math.max(12, maxChars);
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let index = 0;

  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }

  const precision = size >= 100 || index === 0 ? 0 : 1;
  return `${size.toFixed(precision)} ${units[index]}`;
}

function formatEta(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "Estimated time remaining: calculating...";
  }

  const rounded = Math.max(0, Math.ceil(seconds));
  const minutes = Math.floor(rounded / 60);
  const secs = rounded % 60;
  return `Estimated time remaining: ${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function clearGenerationProgressTimer() {
  if (generationProgressTimer) {
    window.clearInterval(generationProgressTimer);
    generationProgressTimer = null;
  }
}

function setGenerationAvailability(isReady, reason = "") {
  subtitleGenerationReady = isReady;
  subtitleGenerationReason = reason;

  if (!isReady) {
    submitJobButton.disabled = true;
    submitJobButton.textContent = "Setup Needed";
    return;
  }

  submitJobButton.disabled = false;
  submitJobButton.textContent = "Generate Video";
}

function updateProgressCard({
  state = "idle",
  label = "Ready to start",
  percent = 0,
  etaText = "Estimated time remaining: --",
  metaText = "No active upload or download."
} = {}) {
  progressCard.dataset.state = state;
  progressLabel.textContent = label;
  progressPercent.textContent = `${Math.round(clamp(percent, 0, 100))}%`;
  progressEta.textContent = etaText;
  progressMeta.textContent = metaText;
  progressFill.style.width = `${clamp(percent, 0, 100)}%`;
}

function resetProgressCard() {
  clearGenerationProgressTimer();
  updateProgressCard();
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function progressStateForJobStatus(status) {
  if (status === "complete") {
    return "complete";
  }
  if (status === "blocked") {
    return "error";
  }
  if (status === "queued" || status === "extracting" || status === "transcribing" || status === "translating" || status === "rendering") {
    return "processing";
  }
  return "idle";
}

function progressLabelForJob(job) {
  if (job.status === "complete") {
    return "Generated video ready";
  }
  if (job.status === "blocked") {
    return "Generation failed";
  }
  return job.current_step || "Generating video";
}

function progressMetaForJob(job) {
  if (job.status === "rendering") {
    return "Rendering the generated video with Subtitle Language 1 and Subtitle Language 2 attached in sync.";
  }

  if (job.status === "translating") {
    return "Translating the shared transcript into the two selected subtitle languages.";
  }

  if (job.status === "extracting" || job.status === "transcribing") {
    return "Finding the original transcript and preparing the shared subtitle timeline.";
  }

  const lastMessage = job.messages?.[job.messages.length - 1]?.text;
  if (lastMessage) {
    return lastMessage;
  }
  if (job.status === "complete") {
    return "The video is ready to play now and can also be downloaded.";
  }
  if (job.status === "blocked") {
    return describeJobStatus(job);
  }
  return "The server is processing your video now.";
}

function updateProgressCardFromJob(job) {
  const etaText =
    typeof job.estimated_seconds_remaining === "number"
      ? formatEta(job.estimated_seconds_remaining)
      : job.status === "complete"
        ? "Estimated time remaining: 00:00"
        : "Estimated time remaining: calculating...";

  updateProgressCard({
    state: progressStateForJobStatus(job.status),
    label: progressLabelForJob(job),
    percent: job.progress_percent ?? 0,
    etaText,
    metaText: progressMetaForJob(job)
  });
}

async function pollJobUntilFinished(jobId) {
  activeJobId = jobId;

  while (activeJobId === jobId) {
    await sleep(1000);

    const response = await fetch(`${getApiBase()}/api/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(await parseErrorResponse(response));
    }

    const job = await response.json();
    renderJob(job);

    if (job.status === "complete" || job.status === "blocked") {
      activeJobId = null;
      return job;
    }
  }

  throw new Error("Video generation was cancelled before completion.");
}

function estimateGenerationDurationMs() {
  const sourceSize = mediaFileInput.files[0]?.size ?? 0;
  const sourceKind = getSelectedSourceKind();
  const baseDurationMs = sourceKind === "external_link" ? 26000 : 15000;
  const sizeDurationMs = sourceSize / (1024 * 1024) * 1700;
  return clamp(baseDurationMs + sizeDurationMs, 15000, 180000);
}

function startGenerationEstimate(startPercent = 58) {
  clearGenerationProgressTimer();

  const startedAt = performance.now();
  const totalDurationMs = estimateGenerationDurationMs();

  generationProgressTimer = window.setInterval(() => {
    const elapsedMs = performance.now() - startedAt;
    const progressRatio = clamp(elapsedMs / totalDurationMs, 0, 1);
    const percent = startPercent + progressRatio * (94 - startPercent);

    if (progressRatio >= 1) {
      updateProgressCard({
        state: "processing",
        label: "Finalizing generated video",
        percent: 94,
        etaText: "Estimated time remaining: almost done",
        metaText: "Finishing the synchronized subtitle render and preparing the downloadable video."
      });
      return;
    }

    updateProgressCard({
      state: "processing",
      label: "Generating synchronized subtitles",
      percent,
      etaText: formatEta((totalDurationMs - elapsedMs) / 1000),
      metaText: "Building one timed transcript, translating Subtitle Language 1 and Subtitle Language 2, then attaching both tracks to the video."
    });
  }, 250);
}

function wrapSubtitleText(text, maxChars) {
  const effectiveMaxChars = subtitleWrapWidth(text, maxChars);

  if (!text.includes(" ") && text.length > effectiveMaxChars) {
    const chunks = [];
    for (let index = 0; index < text.length; index += effectiveMaxChars) {
      chunks.push(text.slice(index, index + effectiveMaxChars));
    }
    return chunks.map((chunk) => escapeHtml(chunk)).join("<br>");
  }

  const words = text.split(" ");
  if (words.length === 1 && text.length <= effectiveMaxChars) {
    return escapeHtml(text);
  }

  const lines = [];
  let current = "";

  words.forEach((word) => {
    const attempt = current ? `${current} ${word}` : word;
    if (attempt.length > effectiveMaxChars && current) {
      lines.push(current);
      current = word;
      return;
    }
    current = attempt;
  });

  if (current) {
    lines.push(current);
  }

  return lines.map((line) => escapeHtml(line)).join("<br>");
}

function updateLanguageSummary() {
  const summaryParts = [
    `Original: ${getLabelForCode(nativeLanguageSelect.value)}`,
    `Subtitle 1: ${getLabelForCode(targetLanguageASelect.value)}`,
    `Subtitle 2: ${getLabelForCode(targetLanguageBSelect.value)}`
  ];

  languageSummary.innerHTML = "";
  summaryParts.forEach((part) => {
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.textContent = part;
    languageSummary.appendChild(chip);
  });
}

function findFallbackLanguage(exclusions) {
  return languageOptions.find((option) => !exclusions.includes(option.code))?.code ?? languageOptions[0].code;
}

function ensureDistinctTargets() {
  if (targetLanguageASelect.value === nativeLanguageSelect.value) {
    targetLanguageASelect.value = findFallbackLanguage([nativeLanguageSelect.value, targetLanguageBSelect.value]);
  }

  if (
    targetLanguageBSelect.value === nativeLanguageSelect.value ||
    targetLanguageBSelect.value === targetLanguageASelect.value
  ) {
    targetLanguageBSelect.value = findFallbackLanguage([nativeLanguageSelect.value, targetLanguageASelect.value]);
  }

  if (targetLanguageASelect.value === targetLanguageBSelect.value) {
    targetLanguageASelect.value = findFallbackLanguage([nativeLanguageSelect.value, targetLanguageBSelect.value]);
  }
}

function applyTheme(theme) {
  const themes = {
    cinema: {
      laneA: "rgba(118, 224, 194, 0.18)",
      laneB: "rgba(255, 207, 125, 0.18)",
      borderA: "rgba(118, 224, 194, 0.36)",
      borderB: "rgba(255, 207, 125, 0.36)"
    },
    soft: {
      laneA: "rgba(255, 255, 255, 0.16)",
      laneB: "rgba(171, 198, 255, 0.2)",
      borderA: "rgba(255, 255, 255, 0.34)",
      borderB: "rgba(171, 198, 255, 0.34)"
    },
    broadcast: {
      laneA: "rgba(10, 10, 10, 0.58)",
      laneB: "rgba(28, 34, 68, 0.68)",
      borderA: "rgba(255, 255, 255, 0.42)",
      borderB: "rgba(118, 224, 194, 0.42)"
    }
  };

  const selectedTheme = themes[theme];
  trackA.style.background = selectedTheme.laneA;
  trackB.style.background = selectedTheme.laneB;
  trackA.style.borderColor = selectedTheme.borderA;
  trackB.style.borderColor = selectedTheme.borderB;
}

function renderPreview() {
  ensureDistinctTargets();

  const laneA = targetLanguageASelect.value;
  const laneB = targetLanguageBSelect.value;
  const maxChars = Number(maxCharsInput.value);

  trackA.innerHTML = wrapSubtitleText(sampleSubtitleCopy[laneA], maxChars);
  trackB.innerHTML = wrapSubtitleText(sampleSubtitleCopy[laneB], maxChars);

  document.documentElement.style.setProperty("--safe-area", `${safeAreaInput.value}%`);
  document.documentElement.style.setProperty("--track-gap", `${trackGapInput.value}px`);

  safeAreaValue.textContent = safeAreaInput.value;
  trackGapValue.textContent = trackGapInput.value;
  maxCharsValue.textContent = maxCharsInput.value;

  updateLanguageSummary();
  applyTheme(themeSelect.value);

  const displayWindow = 18 + Number(trackGapInput.value) / 7;
  const startSecond = Math.floor(displayWindow);
  const endSecond = startSecond + 4;
  timingPreview.textContent = `00:${String(startSecond).padStart(2, "0")} - 00:${String(endSecond).padStart(2, "0")}`;

  subtitleStage.setAttribute("data-native-language", nativeLanguageSelect.value);
  renderPayloadPreview();
  renderProcessingPlan();
}

function setActiveSourceCard(clickedCard) {
  sourceCards.forEach((card) => {
    card.classList.toggle("active", card === clickedCard);
  });

  renderPayloadPreview();
  renderProcessingPlan();
}

function setSourceKind(kind) {
  const normalizedKind = kind.replaceAll("_", "-");
  const matchingCard = [...sourceCards].find((card) => card.dataset.sourceCard === normalizedKind);
  if (matchingCard) {
    setActiveSourceCard(matchingCard);
  }
}

function getSelectedSourceKind() {
  return document.querySelector(".source-card.active")?.dataset.sourceCard?.replaceAll("-", "_") ?? "upload_video";
}

function buildPayload() {
  return {
    kind: getSelectedSourceKind(),
    provider: providerSelect.value,
    output_mode: outputModeSelect.value,
    source_url: sourceUrlInput.value || null,
    original_language: nativeLanguageSelect.value,
    target_languages: [targetLanguageASelect.value, targetLanguageBSelect.value],
    layout: {
      safe_area_percent: Number(safeAreaInput.value),
      track_gap_px: Number(trackGapInput.value),
      max_chars_per_line: Number(maxCharsInput.value),
      theme: themeSelect.value
    },
    source_filename: mediaFileInput.files[0]?.name ?? null,
    subtitles_filename: subtitleFileInput?.files?.[0]?.name ?? null
  };
}

function renderPayloadPreview() {
  if (payloadPreview) {
    payloadPreview.textContent = JSON.stringify(buildPayload(), null, 2);
  }
}

function setJobState(label, description) {
  jobStatusBadge.textContent = label;
  jobStatusBadge.dataset.state = String(label).toLowerCase();
  jobStatusText.textContent = description;
}

function describeJobStatus(job) {
  if (job.status === "complete") {
    return "Your video is ready to play.";
  }
  if (job.status === "blocked") {
    const firstError = job.messages?.find((message) => message.level === "error");
    return firstError?.text || "The video could not be completed yet.";
  }
  return job.current_step || "Your video is being prepared.";
}

function setButtonEnabled(button, enabled) {
  button.classList.toggle("button-disabled", !enabled);
  button.setAttribute("aria-disabled", String(!enabled));
  if ("disabled" in button) {
    button.disabled = !enabled;
  }
}

function setVideoDownloadState({ href = "#", enabled = false, filename = "" } = {}) {
  downloadVideoButton.href = href;
  downloadVideoButton.dataset.href = href;
  downloadVideoButton.dataset.enabled = String(enabled);
  downloadVideoButton.dataset.filename = filename;
  setButtonEnabled(downloadVideoButton, enabled);
  if (!enabled) {
    downloadVideoButton.removeAttribute("download");
  } else {
    downloadVideoButton.setAttribute("download", "");
  }
}

function resetOutputActions() {
  setButtonEnabled(watchNowButton, false);
  setButtonEnabled(downloadLanguageAButton, false);
  setButtonEnabled(downloadLanguageBButton, false);
  setVideoDownloadState();
}

function updateOutputActionsFromJob(job) {
  const hasCues = Boolean(job?.cues?.length);
  const burnedVideoArtifact = getBurnedVideoArtifact(job);

  setButtonEnabled(watchNowButton, Boolean(resultVideo?.src));
  setButtonEnabled(downloadLanguageAButton, hasCues);
  setButtonEnabled(downloadLanguageBButton, hasCues);
  setVideoDownloadState({
    href: burnedVideoArtifact?.download_url ?? "#",
    enabled: Boolean(burnedVideoArtifact),
    filename: burnedVideoArtifact?.filename ?? "",
  });
}

function clearPlaybackSubtitles() {
  trackA.innerHTML = "";
  trackB.innerHTML = "";
}

function clearResultPlayer() {
  currentJob = null;
  subtitleStage.hidden = false;
  releaseResultVideoUrl();
  resultVideo.pause();
  resultVideo.removeAttribute("src");
  resultVideo.load();
  clearPlaybackSubtitles();
  playerLabel.textContent = "Generated video";
  resetOutputActions();
}

function formatCueTime(totalMs) {
  const safeValue = Math.max(0, Math.floor(totalMs));
  const minutes = Math.floor(safeValue / 60000);
  const seconds = Math.floor((safeValue % 60000) / 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function getActiveCue(job, currentTimeMs) {
  return job?.cues?.find((cue) => currentTimeMs >= cue.start_ms && currentTimeMs <= cue.end_ms) ?? null;
}

function updatePlaybackSubtitles() {
  if (!currentJob || !resultVideo || !resultVideo.src) {
    return;
  }

  const activeCue = getActiveCue(currentJob, resultVideo.currentTime * 1000);
  if (!activeCue) {
    clearPlaybackSubtitles();
    return;
  }

  const laneA = currentJob.request.target_languages[0];
  const laneB = currentJob.request.target_languages[1];

  trackA.innerHTML = wrapSubtitleText(
    activeCue.translations[laneA] ?? activeCue.original_text,
    Number(maxCharsInput.value || 28)
  );
  trackB.innerHTML = wrapSubtitleText(
    activeCue.translations[laneB] ?? activeCue.original_text,
    Number(maxCharsInput.value || 28)
  );
  timingPreview.textContent = `${formatCueTime(activeCue.start_ms)} - ${formatCueTime(activeCue.end_ms)}`;
}

function getPlayableSource() {
  if (mediaFileInput.files[0]) {
    releaseResultVideoUrl();
    resultVideoUrl = URL.createObjectURL(mediaFileInput.files[0]);
    return resultVideoUrl;
  }

  const urlValue = sourceUrlInput.value.trim();
  if (/\.(mp4|webm|mov|m4v)$/i.test(urlValue)) {
    return urlValue;
  }

  return null;
}

function setupResultPlayer(job) {
  currentJob = job;
  const burnedVideoArtifact = getBurnedVideoArtifact(job);
  if (burnedVideoArtifact) {
    releaseResultVideoUrl();
    subtitleStage.hidden = true;
    resultVideo.src = burnedVideoArtifact.download_url;
    resultVideo.load();
    playerHint.textContent = "Press play to watch the generated video with both subtitle languages attached.";
    playerLabel.textContent = "Generated video with subtitles";
    clearPlaybackSubtitles();
    return;
  }

  const playableSource = getPlayableSource();

  if (!playableSource) {
    subtitleStage.hidden = false;
    playerHint.textContent = "The generated subtitles are ready. Add a playable video upload if you want in-page playback.";
    playerLabel.textContent = "Playable video unavailable";
    resultVideo.removeAttribute("src");
    resultVideo.load();
    clearPlaybackSubtitles();
    return;
  }

  subtitleStage.hidden = false;
  resultVideo.src = playableSource;
  resultVideo.load();
  playerHint.textContent = "Press play to watch the video with the new subtitle lanes.";
  playerLabel.textContent = "Generated video";
  updatePlaybackSubtitles();
}

function renderMessageItems(messages, providerNotes) {
  const items = [
    ...providerNotes.map((text) => ({ level: "info", text })),
    ...messages
  ];

  if (!items.length) {
    jobMessages.innerHTML = `<p class="empty-copy">Provider and processing notes will appear here.</p>`;
    return;
  }

  jobMessages.innerHTML = items
    .map((item) => `
      <div class="message-item">
        <strong>${escapeHtml(item.level.toUpperCase())}</strong>
        <p>${escapeHtml(item.text)}</p>
      </div>
    `)
    .join("");
}

async function parseErrorResponse(response) {
  const contentType = response.headers.get("content-type") || "";

  try {
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      if (Array.isArray(payload.detail)) {
        return payload.detail.map((item) => item.msg || JSON.stringify(item)).join(" ");
      }
      if (typeof payload.detail === "string") {
        return payload.detail;
      }
      return JSON.stringify(payload);
    }

    const text = await response.text();
    return text || `Request failed with status ${response.status}.`;
  } catch (error) {
    return `Request failed with status ${response.status}.`;
  }
}

function parseXhrError(xhr) {
  try {
    const payload = JSON.parse(xhr.responseText);
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item.msg || JSON.stringify(item)).join(" ");
    }
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    return xhr.responseText || `Request failed with status ${xhr.status}.`;
  } catch (error) {
    return xhr.responseText || `Request failed with status ${xhr.status}.`;
  }
}

function submitJobWithProgress(formData) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const requestStartedAt = performance.now();
    const hasMediaUpload = Boolean(mediaFileInput.files[0]);

    xhr.open("POST", `${getApiBase()}/api/jobs/submit`);
    xhr.responseType = "json";

    xhr.upload.addEventListener("progress", (event) => {
      if (!hasMediaUpload) {
        return;
      }

      if (!event.lengthComputable) {
        updateProgressCard({
          state: "uploading",
          label: "Uploading source video",
          percent: 18,
          etaText: "Estimated time remaining: calculating...",
          metaText: `Sending the source video to ${getApiHostLabel()}.`
        });
        return;
      }

      const elapsedSeconds = Math.max((performance.now() - requestStartedAt) / 1000, 0.2);
      const speed = event.loaded / elapsedSeconds;
      const etaSeconds = speed > 0 ? (event.total - event.loaded) / speed : NaN;

      updateProgressCard({
        state: "uploading",
        label: "Uploading source video",
        percent: (event.loaded / event.total) * 55,
        etaText: formatEta(etaSeconds),
        metaText: `${formatBytes(event.loaded)} of ${formatBytes(event.total)} uploaded`
      });
    });

    xhr.addEventListener("load", () => {
      clearGenerationProgressTimer();
      if (xhr.status >= 200 && xhr.status < 300) {
        const payload =
          xhr.response && typeof xhr.response === "object" ? xhr.response : JSON.parse(xhr.responseText || "{}");
        resolve(payload);
        return;
      }
      reject(new Error(parseXhrError(xhr)));
    });

    xhr.addEventListener("error", () => {
      clearGenerationProgressTimer();
      reject(new Error(`The app could not reach ${getApiHostLabel()}.`));
    });

    if (!hasMediaUpload) {
      updateProgressCard({
        state: "processing",
        label: "Sending request",
        percent: 10,
        etaText: "Estimated time remaining: calculating...",
        metaText: `Sending the request to ${getApiHostLabel()}.`
      });
    }

    xhr.send(formData);
  });
}

function extractFilenameFromContentDisposition(value) {
  if (!value) {
    return "";
  }

  const match = value.match(/filename="?([^"]+)"?/i);
  return match?.[1] ?? "";
}

function saveBlobToDisk(blob, filename) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function downloadVideoWithProgress() {
  const href = downloadVideoButton.dataset.href || downloadVideoButton.getAttribute("href");
  const fallbackFilename = downloadVideoButton.dataset.filename || "dual-subtitle-video.mp4";
  const downloadLabel = (downloadVideoButton.textContent || "Download Video").trim();

  if (!href || href === "#" || downloadVideoButton.dataset.enabled !== "true") {
    return;
  }

  if (downloadVideoButton.dataset.busy === "true") {
    return;
  }

  downloadVideoButton.dataset.busy = "true";
  downloadVideoButton.classList.add("button-disabled");

  try {
    updateProgressCard({
      state: "downloading",
      label: "Starting download",
      percent: 0,
      etaText: "Estimated time remaining: calculating...",
      metaText: `Preparing ${downloadLabel.toLowerCase()} for download.`
    });

    const response = await fetch(href);
    if (!response.ok) {
      throw new Error(await parseErrorResponse(response));
    }

    const totalBytes = Number(response.headers.get("content-length") || 0);
    const filename = extractFilenameFromContentDisposition(response.headers.get("content-disposition")) || fallbackFilename;

    if (!response.body || !totalBytes) {
      const blob = await response.blob();
      saveBlobToDisk(blob, filename);
      updateProgressCard({
        state: "complete",
        label: "Download complete",
        percent: 100,
        etaText: "Estimated time remaining: 00:00",
        metaText: `${filename} has finished downloading.`
      });
      return;
    }

    const startedAt = performance.now();
    const reader = response.body.getReader();
    const chunks = [];
    let receivedBytes = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      chunks.push(value);
      receivedBytes += value.length;

      const elapsedSeconds = Math.max((performance.now() - startedAt) / 1000, 0.2);
      const speed = receivedBytes / elapsedSeconds;
      const etaSeconds = speed > 0 ? (totalBytes - receivedBytes) / speed : NaN;

      updateProgressCard({
        state: "downloading",
        label: downloadLabel,
        percent: (receivedBytes / totalBytes) * 100,
        etaText: formatEta(etaSeconds),
        metaText: `${formatBytes(receivedBytes)} of ${formatBytes(totalBytes)} downloaded`
      });
    }

    const blob = new Blob(chunks, { type: response.headers.get("content-type") || "application/octet-stream" });
    saveBlobToDisk(blob, filename);
    updateProgressCard({
      state: "complete",
      label: "Download complete",
      percent: 100,
      etaText: "Estimated time remaining: 00:00",
      metaText: `${filename} has finished downloading.`
    });
  } catch (error) {
    updateProgressCard({
      state: "error",
      label: "Download failed",
      percent: 0,
      etaText: "Estimated time remaining: --",
      metaText: error.message || "The file could not be downloaded."
    });
  } finally {
    downloadVideoButton.dataset.busy = "false";
    if (downloadVideoButton.dataset.enabled === "true") {
      downloadVideoButton.classList.remove("button-disabled");
    }
  }
}

async function watchGeneratedVideo() {
  if (watchNowButton.disabled || !resultVideo?.src) {
    return;
  }

  resultVideo.scrollIntoView({ behavior: "smooth", block: "center" });
  resultVideo.setAttribute("tabindex", "-1");
  resultVideo.focus({ preventScroll: true });

  try {
    await resultVideo.play();
    playerHint.textContent = "Playing the generated video with the two subtitle lanes.";
  } catch (error) {
    playerHint.textContent = "Use the video controls to start playback.";
  }
}

function formatSrtTimestamp(totalMs) {
  const safeValue = Math.max(0, Math.floor(totalMs));
  const hours = Math.floor(safeValue / 3600000);
  const minutes = Math.floor((safeValue % 3600000) / 60000);
  const seconds = Math.floor((safeValue % 60000) / 1000);
  const milliseconds = safeValue % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")},${String(milliseconds).padStart(3, "0")}`;
}

function buildSrtForLanguage(job, languageCode) {
  return job.cues
    .map((cue, index) => {
      const text = cue.translations?.[languageCode] || cue.original_text || "";
      return [
        String(index + 1),
        `${formatSrtTimestamp(cue.start_ms)} --> ${formatSrtTimestamp(cue.end_ms)}`,
        text,
      ].join("\n");
    })
    .join("\n\n");
}

function downloadLanguageSrt(laneIndex) {
  if (!currentJob?.cues?.length) {
    return;
  }

  const languageCode = currentJob.request.target_languages[laneIndex];
  const laneLabel = laneIndex === 0 ? "language-1" : "language-2";
  const srtText = buildSrtForLanguage(currentJob, languageCode);
  const blob = new Blob([srtText], { type: "application/x-subrip;charset=utf-8" });
  saveBlobToDisk(blob, `${currentJob.job_id}-${laneLabel}-${languageCode}.srt`);
  updateProgressCard({
    state: "complete",
    label: "SRT download ready",
    percent: 100,
    etaText: "Estimated time remaining: 00:00",
    metaText: `${laneLabel} subtitle file has been downloaded.`,
  });
}

function releaseResultVideoUrl() {
  if (resultVideoUrl) {
    URL.revokeObjectURL(resultVideoUrl);
    resultVideoUrl = null;
  }
}

function getBurnedVideoArtifact(job) {
  return job?.artifacts?.find((artifact) => artifact.kind === "burned_video") ?? null;
}

function validateSubmission() {
  if (!subtitleGenerationReady) {
    return subtitleGenerationReason || "Real subtitle generation is not configured yet.";
  }

  const sourceKind = getSelectedSourceKind();
  const hasMediaFile = Boolean(mediaFileInput.files[0]);
  const hasSourceUrl = Boolean(sourceUrlInput.value.trim());

  if (!hasMediaFile && !hasSourceUrl) {
    return "Add a video file or paste a link before you generate the video.";
  }

  if (sourceKind === "upload_video" && !hasMediaFile) {
    return "Choose a video file for upload, or switch to Paste Link and add a link.";
  }

  if (sourceKind === "external_link" && !hasSourceUrl) {
    return "Paste a link before you generate the video.";
  }

  if (targetLanguageASelect.value === targetLanguageBSelect.value) {
    return "Subtitle Language 1 and Subtitle Language 2 must be different.";
  }

  if (
    nativeLanguageSelect.value === targetLanguageASelect.value ||
    nativeLanguageSelect.value === targetLanguageBSelect.value
  ) {
    return "Both subtitle languages must be different from the original language.";
  }

  return null;
}

function localSetupIssuesFromHealth(health) {
  const issues = [];

  if (!health.offline_transcription_ready && !health.openai_configured) {
    issues.push("offline Whisper transcription is not installed");
  }

  if (!health.offline_translation_ready && !health.openai_configured) {
    issues.push("offline translation is not installed");
  }

  if (health.offline_translation_ready && !health.chinese_conversion_ready) {
    issues.push("Chinese script conversion is not installed yet");
  }

  return issues;
}

function localSetupMessageFromHealth(health) {
  const issues = localSetupIssuesFromHealth(health);
  if (!issues.length) {
    return "The local subtitle stack is ready.";
  }

  return `Run setup-local-ai.bat to install ${issues.join(", ")}.`;
}

function setupMessageFromHealth(health) {
  if (isUsingLocalApi()) {
    return localSetupMessageFromHealth(health);
  }

  const issues = localSetupIssuesFromHealth(health);
  if (!issues.length) {
    return "The hosted subtitle backend is ready.";
  }

  return `The hosted backend is reachable, but it still needs a real transcription and translation provider configured. Missing: ${issues.join(", ")}.`;
}

async function checkApiAvailability() {
  if (await redirectFromFileModeIfPossible()) {
    return;
  }

  try {
    const response = await fetch(`${getApiBase()}/api/health`);
    if (!response.ok) {
      throw new Error(`Health check failed with status ${response.status}.`);
    }
    const health = await response.json();
    if (!health.subtitle_generation_ready && !health.demo_fallback_enabled) {
      const setupMessage = setupMessageFromHealth(health);
      const localApi = isUsingLocalApi();
      setGenerationAvailability(
        false,
        setupMessage
      );
      renderMessageItems(
        [
          {
            level: "warning",
            text: setupMessage
          }
        ],
        []
      );
      setJobState(
        "Setup Needed",
        localApi
          ? "Install the local subtitle tools before generating a video."
          : "Configure the hosted backend before generating a video."
      );
      updateProgressCard({
        state: "error",
        label: "Setup needed",
        percent: 0,
        etaText: "Estimated time remaining: --",
        metaText: localApi
          ? "Run setup-local-ai.bat, restart start-local.bat, then refresh this page."
          : "Add a cloud translation/transcription provider to the hosted backend, then refresh this page."
      });
      clearResultPlayer();
      return;
    }

    setGenerationAvailability(true);
  } catch (error) {
    const configuredApiBase = getConfiguredApiBase();
    const localApi = isUsingLocalApi();
    setGenerationAvailability(
      false,
      configuredApiBase
        ? `The hosted backend at ${configuredApiBase} is not reachable.`
        : "Connect the app to a hosted backend before generating a video."
    );
    renderMessageItems(
      [
        {
          level: "error",
          text: configuredApiBase
            ? `The app could not reach the hosted API at ${configuredApiBase}. ${error.message}`
            : localApi
              ? "This app is still using the local development API. Use a hosted backend URL so translation does not depend on this PC."
              : `The app could not reach the hosted API. ${error.message}`
        }
      ],
      []
    );
    setJobState("Error", `${getApiHostLabel()} is not reachable.`);
    updateProgressCard({
      state: "error",
      label: "Server unavailable",
      percent: 0,
      etaText: "Estimated time remaining: --",
      metaText: configuredApiBase
        ? "Check that the hosted backend is deployed, awake, and allowing browser requests from this site."
        : "Configure a hosted backend URL for production use."
    });
    clearResultPlayer();
  }
}

function renderArtifactItems(artifacts) {
  if (!artifacts.length) {
    artifactList.innerHTML = `<p class="empty-copy">Generated subtitle downloads and overlay payloads will appear here.</p>`;
    setVideoDownloadState();
    return;
  }

  artifactList.innerHTML = artifacts
    .map((artifact) => `
      <div class="artifact-item">
        <strong>${escapeHtml(artifact.kind)}</strong>
        <p>${escapeHtml(artifact.filename)}</p>
        <p><a href="${escapeHtml(artifact.download_url)}" target="_blank" rel="noreferrer">Download</a></p>
      </div>
    `)
    .join("");
}

function renderCueItems(job) {
  if (!job.cues.length) {
    cueList.innerHTML = `<p class="empty-copy">The first translated subtitle cues will appear here after processing.</p>`;
    clearPlaybackSubtitles();
    return;
  }

  const laneA = job.request.target_languages[0];
  const laneB = job.request.target_languages[1];
  const previewCues = job.cues.slice(0, 4);

  cueList.innerHTML = previewCues
    .map((cue) => `
      <div class="cue-item">
        <strong>${escapeHtml(cue.cue_id)} | ${escapeHtml(cue.start_ms)}ms - ${escapeHtml(cue.end_ms)}ms</strong>
        <p>Original: ${escapeHtml(cue.original_text)}</p>
        <p>${escapeHtml(getLabelForCode(laneA))}: ${escapeHtml(cue.translations[laneA] ?? "")}</p>
        <p>${escapeHtml(getLabelForCode(laneB))}: ${escapeHtml(cue.translations[laneB] ?? "")}</p>
      </div>
    `)
    .join("");

  trackA.innerHTML = wrapSubtitleText(job.cues[0].translations[laneA] ?? job.cues[0].original_text, Number(maxCharsInput.value));
  trackB.innerHTML = wrapSubtitleText(job.cues[0].translations[laneB] ?? job.cues[0].original_text, Number(maxCharsInput.value));
}

function renderJob(job) {
  setJobState(job.status, describeJobStatus(job));
  renderMessageItems(job.messages, job.provider_notes);
  renderArtifactItems(job.artifacts);
  renderCueItems(job);
  updateProgressCardFromJob(job);

  if (job.status === "complete") {
    setupResultPlayer(job);
    updateOutputActionsFromJob(job);
    return;
  }

  if (job.status === "blocked") {
    clearResultPlayer();
    playerHint.textContent = "Fix the issue above, then generate the video again.";
    return;
  }

  resetOutputActions();
  playerHint.textContent = "Your generated video will appear here as soon as the render completes.";
}

function describeSource() {
  const kind = getSelectedSourceKind();

  if (kind === "external_link") {
    return sourceUrlInput.value
      ? `Receive a ${providerSelect.options[providerSelect.selectedIndex].text} link and queue remote ingestion for ${sourceUrlInput.value}.`
      : "Receive a provider link and queue an ingest worker for remote subtitle or audio access.";
  }

  return mediaFileInput.files[0]?.name
    ? `Receive ${mediaFileInput.files[0].name} as the source video and extract audio and frames for timed transcript generation.`
    : "Receive a local video upload and create the original timed transcript from the media audio.";
}

function describeTranscriptStep() {
  return `Detect or confirm ${getLabelForCode(nativeLanguageSelect.value)} as the original language, then generate transcript cues with start and end times.`;
}

function describeRenderStep() {
  return `Attach Subtitle Language 1 and Subtitle Language 2 to the video with ${trackGapInput.value}px of buffer and a ${safeAreaInput.value}% bottom safe area, then make the result ready to play here and download when available.`;
}

function renderProcessingPlan() {
  const sourceDescription = escapeHtml(describeSource());
  const transcriptDescription = escapeHtml(describeTranscriptStep());
  const renderDescription = escapeHtml(describeRenderStep());
  const laneALabel = escapeHtml(getLabelForCode(targetLanguageASelect.value));
  const laneBLabel = escapeHtml(getLabelForCode(targetLanguageBSelect.value));

  processSummary.innerHTML = `
    <article class="summary-card">
      <h3>Source</h3>
      <p>${sourceDescription}</p>
    </article>
    <article class="summary-card">
      <h3>Transcript</h3>
      <p>${transcriptDescription}</p>
    </article>
    <article class="summary-card">
      <h3>Render</h3>
      <p>${renderDescription}</p>
    </article>
  `;

  statusList.innerHTML = `
    <div class="status-item">
      <span>1</span>
      <div>
        <strong>Source received</strong>
        <p>${sourceDescription}</p>
      </div>
    </div>
    <div class="status-item">
      <span>2</span>
      <div>
        <strong>Timed transcript created</strong>
        <p>${transcriptDescription}</p>
      </div>
    </div>
    <div class="status-item">
      <span>3</span>
      <div>
        <strong>Dual-language translation generated</strong>
        <p>Translate every original cue into ${laneALabel} and ${laneBLabel} while keeping both outputs bound to the same timestamps.</p>
      </div>
    </div>
    <div class="status-item">
      <span>4</span>
      <div>
        <strong>Video-ready subtitle output prepared</strong>
        <p>${renderDescription}</p>
      </div>
    </div>
  `;
}

async function submitJob() {
  const validationError = validateSubmission();
  if (validationError) {
    renderMessageItems([{ level: "error", text: validationError }], []);
    setJobState("Error", validationError);
    playerHint.textContent = "Fix the issue above, then generate the video again.";
    resetOutputActions();
    clearResultPlayer();
    updateProgressCard({
      state: "error",
      label: "Cannot start generation",
      percent: 0,
      etaText: "Estimated time remaining: --",
      metaText: validationError
    });
    return;
  }

  const formData = new FormData();
  formData.append("metadata", JSON.stringify(buildPayload()));

  if (mediaFileInput.files[0]) {
    formData.append("media_file", mediaFileInput.files[0]);
  }

  submitJobButton.disabled = true;
  submitJobButton.textContent = "Processing...";
  setJobState("Submitting", "Generating your video.");
  resetOutputActions();
  clearResultPlayer();
  clearPlaybackSubtitles();

  updateProgressCard({
    state: "uploading",
    label: "Preparing request",
    percent: 2,
    etaText: "Estimated time remaining: calculating...",
    metaText: "Collecting the source video and language choices."
  });

  try {
    const payload = await submitJobWithProgress(formData);
    renderJob(payload);
    if (payload.job_id && payload.status !== "complete" && payload.status !== "blocked") {
      await pollJobUntilFinished(payload.job_id);
    }
  } catch (error) {
    activeJobId = null;
    const friendlyMessage =
      error instanceof TypeError && window.location.protocol === "file:" && !getConfiguredApiBase()
        ? "This file page does not have a hosted API configured. Open it with ?api=https://your-hosted-backend.example.com or deploy it with api-config.js set to your hosted backend."
        : error.message || "The request failed before the video could be generated.";
    renderMessageItems([{ level: "error", text: friendlyMessage }], []);
    renderArtifactItems([]);
    renderCueItems({ cues: [], request: { target_languages: [] } });
    setJobState("Error", friendlyMessage);
    playerHint.textContent = "Fix the issue above, then generate the video again.";
    clearResultPlayer();
    updateProgressCard({
      state: "error",
      label: "Generation failed",
      percent: 0,
      etaText: "Estimated time remaining: --",
      metaText: friendlyMessage
    });
  } finally {
    clearGenerationProgressTimer();
    setGenerationAvailability(subtitleGenerationReady, subtitleGenerationReason);
  }
}

populateLanguageSelect(nativeLanguageSelect, "ja");
populateLanguageSelect(targetLanguageASelect, "zh-Hans");
populateLanguageSelect(targetLanguageBSelect, "en");

[nativeLanguageSelect, targetLanguageASelect, targetLanguageBSelect].forEach((select) => {
  select.addEventListener("change", renderPreview);
});

[safeAreaInput, trackGapInput, maxCharsInput].forEach((input) => {
  input.addEventListener("input", renderPreview);
});

themeSelect.addEventListener("change", renderPreview);
providerSelect.addEventListener("change", () => {
  renderPayloadPreview();
  renderProcessingPlan();
});
sourceUrlInput.addEventListener("input", () => {
  if (sourceUrlInput.value.trim()) {
    setSourceKind("external_link");
  }
  renderPayloadPreview();
  renderProcessingPlan();
});
mediaFileInput.addEventListener("change", () => {
  if (mediaFileInput.files[0]) {
    setSourceKind("upload_video");
  }
  renderPayloadPreview();
  renderProcessingPlan();
});
if (subtitleFileInput) {
  subtitleFileInput.addEventListener("change", () => {
    renderPayloadPreview();
    renderProcessingPlan();
  });
}
generatePayloadButton.addEventListener("click", renderPayloadPreview);
submitJobButton.addEventListener("click", submitJob);
watchNowButton.addEventListener("click", watchGeneratedVideo);
downloadLanguageAButton.addEventListener("click", () => downloadLanguageSrt(0));
downloadLanguageBButton.addEventListener("click", () => downloadLanguageSrt(1));
downloadVideoButton.addEventListener("click", (event) => {
  event.preventDefault();
  downloadVideoWithProgress();
});
simulateProcessingButton.addEventListener("click", renderProcessingPlan);

sourceCards.forEach((card) => {
  card.addEventListener("click", () => setActiveSourceCard(card));
});

if (resultVideo) {
  ["timeupdate", "seeked", "loadedmetadata", "play"].forEach((eventName) => {
    resultVideo.addEventListener(eventName, updatePlaybackSubtitles);
  });
  resultVideo.addEventListener("ended", clearPlaybackSubtitles);
}

resetOutputActions();
resetProgressCard();
renderPreview();
renderProcessingPlan();
checkApiAvailability();
