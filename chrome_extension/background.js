// Service worker (Manifest V3): el unico lugar que toca la API sensible (chrome.cookies).
// No persiste nada - cada mensaje dispara una lectura fresca de la cookie y la devuelve
// una sola vez al content script que la pidio.

const MOODLE_URL = "https://moodle-108854-0.cloudclusters.net";
const COOKIE_NAME = "MoodleSession";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.action !== "getMoodleCookie") return false;

  chrome.cookies.get({ url: MOODLE_URL, name: COOKIE_NAME }, (cookie) => {
    if (chrome.runtime.lastError) {
      sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      return;
    }
    if (!cookie || !cookie.value) {
      sendResponse({
        ok: false,
        error: "No se encontró la cookie MoodleSession. Iniciá sesión en Moodle en este navegador primero.",
      });
      return;
    }
    sendResponse({ ok: true, value: cookie.value });
  });

  return true; // respuesta asincrona
});
