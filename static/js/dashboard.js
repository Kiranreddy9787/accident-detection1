const menuButton = document.getElementById("menuButton");
const sidebar = document.getElementById("sidebar");
const analysisVideo = document.getElementById("analysisVideo");
const playbackTime = document.getElementById("playbackTime");
const analysisForm = document.getElementById("analysisForm");
const analysisProgress = document.getElementById("analysisProgress");
const analysisProgressBar = document.getElementById("analysisProgressBar");
const analysisStatus = document.getElementById("analysisStatus");

if (menuButton && sidebar) menuButton.addEventListener("click", () => sidebar.classList.toggle("open"));
if (analysisVideo && playbackTime) {
  analysisVideo.addEventListener("timeupdate", () => {
    const seconds = Math.floor(analysisVideo.currentTime || 0);
    playbackTime.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  });
}

if (analysisForm) {
  analysisForm.addEventListener("submit", event => {
    event.preventDefault();
    const button = analysisForm.querySelector("button[type='submit']");
    if (!button) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.querySelector(".button-label").textContent = "Analyzing video…";
    const note = analysisForm.querySelector(".analysis-note");
    if (note) note.textContent = "Analysis is running. This can take a few minutes for longer videos.";

    analysisProgress.hidden = false;
    analysisProgressBar.value = 0;
    analysisStatus.textContent = "Loading pretrained YOLO model…";
    let polling = true;
    const pollProgress = async () => {
      if (!polling) return;
      try {
        const response = await fetch(analysisForm.dataset.progressUrl, { cache: "no-store" });
        if (response.ok) {
          const state = await response.json();
          analysisProgressBar.value = state.progress || 0;
          const frames = state.total_frames
            ? ` · frame ${state.current_frame || 0} of ${state.total_frames}`
            : "";
          analysisStatus.textContent = `${state.message || "Analyzing video…"}${frames}`;
        }
      } catch (_error) {
        analysisStatus.textContent = "Analysis is running; progress updates are temporarily unavailable.";
      }
      if (polling) window.setTimeout(pollProgress, 500);
    };
    pollProgress();

    const xhr = new XMLHttpRequest();
    xhr.open("POST", analysisForm.action);
    xhr.addEventListener("load", () => {
      polling = false;
      if (xhr.status >= 500) {
        analysisStatus.textContent = `Analysis failed with server error ${xhr.status}. Check the Flask terminal and try again.`;
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.querySelector(".button-label").textContent = "Try analysis again";
        return;
      }
      window.location.assign(xhr.responseURL || "/");
    });
    xhr.addEventListener("error", () => {
      polling = false;
      analysisStatus.textContent = "The analysis request lost its connection. Reload the dashboard and try again.";
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.querySelector(".button-label").textContent = "Try analysis again";
    });
    xhr.send(new FormData(analysisForm));
  });
}
