/* DEBUG: temporary debug script */
async function loadDebug() {
  try {
    const res = await fetch('/api/debug');
    const data = await res.json();
    const div = document.createElement('pre');
    div.id = 'debug';
    div.textContent =
      `Coingecko command: ${data.coingecko_command}\n` +
      `API key: ${data.api_key}\n` +
      `Ping command: ${data.ping_command}\n` +
      `Ping response: ${data.ping_response}`;
    document.body.appendChild(div);
  } catch (err) {
    console.error('debug error', err);
  }
}
loadDebug();
