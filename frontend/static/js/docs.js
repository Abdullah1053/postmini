// Documentation and AI Prompt Helpers
function copyPromptText() {
  const prompt = document.getElementById("aiPromptText").innerText;
  navigator.clipboard.writeText(prompt);
  showToast("AI Prompt copied to clipboard!");
}

function copySampleJson() {
  const sample = document.getElementById("sampleJsonText").innerText;
  navigator.clipboard.writeText(sample);
  showToast("Sample JSON copied to clipboard!");
}

async function importSampleDirectly() {
  const sample = document.getElementById("sampleJsonText").innerText;
  try {
    const parsed = JSON.parse(sample);
    const data = await ApiService.importCollection(parsed);
    await loadProjects();
    if (data.project && data.project.id) {
      selectProject(data.project.id);
    }
    switchMainView('client');
    showToast("Sample collection imported successfully!");
  } catch (e) {
    alert("Failed to import sample: " + e.message);
  }
}
