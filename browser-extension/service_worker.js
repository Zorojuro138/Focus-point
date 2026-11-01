const FOCUSPILOT = "http://127.0.0.1:43821";
let refreshTimer;

async function sendActivePage() {
  try {
    const stateResponse = await fetch(`${FOCUSPILOT}/v1/state`, {
      cache: "no-store",
    });
    if (!stateResponse.ok || !(await stateResponse.json()).monitoring) return;

    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab?.url || !tab.title || !/^https?:\/\//i.test(tab.url)) return;
    const pageUrl = new URL(tab.url);
    pageUrl.search = "";
    pageUrl.hash = "";

    await fetch(`${FOCUSPILOT}/v1/tab`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: tab.title,
        url: pageUrl.href,
        browser: /Edg\//i.test(navigator.userAgent) ? "msedge.exe" : "chrome.exe",
      }),
      cache: "no-store",
    });
  } catch {
    // FocusPilot may be closed or no session may be active.
  }
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(sendActivePage, 300);
}

chrome.tabs.onActivated.addListener(scheduleRefresh);
chrome.tabs.onUpdated.addListener((_tabId, change) => {
  if (change.status === "complete" || change.title || change.url) scheduleRefresh();
});
chrome.windows.onFocusChanged.addListener(scheduleRefresh);
chrome.runtime.onStartup.addListener(scheduleRefresh);
chrome.runtime.onInstalled.addListener(scheduleRefresh);
chrome.alarms.create("focuspilot-refresh", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(scheduleRefresh);
