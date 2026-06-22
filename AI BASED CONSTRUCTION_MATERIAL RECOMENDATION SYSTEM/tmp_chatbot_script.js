
function fillChip(el) {
  document.getElementById('userInput').value = el.textContent.trim();
  send();
}
async function send() {
  const input = document.getElementById('userInput');
  const msg   = input.value.trim();
  if (!msg) return;
  input.value = '';
  addMsg(msg, 'user');
  const loading = addMsg('Analysing your project...', 'bot loading');
  try {
    const r = await fetch('/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const d = await r.json();
    loading.remove();
    if (d.reply) {
      addMsg(d.reply, 'bot');
    } else {
      addMsg('Error: No response from server', 'bot');
    }
  } catch(e) {
    loading.remove();
    console.error('Error:', e);
    addMsg('Sorry, something went wrong. Error: ' + e.message, 'bot');
  }
}
function addMsg(text, cls) {
  const box = document.getElementById('chatBox');
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  const safeText = text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
  div.innerHTML = safeText.split('\n').join('<br>');
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}
