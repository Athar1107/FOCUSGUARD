const PORT = 5678;
const SERVER = `http://127.0.0.1:${PORT}`;

async function sendUrl(url) {
  if (!url || url.startsWith("chrome://") || url.startsWith("edge://")) return;
  try {
    await fetch(`${SERVER}/url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, timestamp: new Date().toISOString(), browser: "chrome" })
    });
  } catch (_) {}
}

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const tab = await chrome.tabs.get(activeInfo.tabId);
  if (tab.url) sendUrl(tab.url);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.active && tab.url) sendUrl(tab.url);
});
