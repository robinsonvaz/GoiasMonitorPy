// GoiasMonitorPy — global JavaScript

// ----- Mobile sidebar -----
function toggleMobileMenu() {
  const sidebar = document.getElementById('sidebar');
  const openIcon = document.getElementById('menu-open-icon');
  const closeIcon = document.getElementById('menu-close-icon');

  const isOpen = sidebar.classList.toggle('open');
  openIcon.style.display = isOpen ? 'none' : '';
  closeIcon.style.display = isOpen ? '' : 'none';
}

function closeMobileMenu() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    sidebar.classList.remove('open');
    const openIcon = document.getElementById('menu-open-icon');
    const closeIcon = document.getElementById('menu-close-icon');
    if (openIcon) openIcon.style.display = '';
    if (closeIcon) closeIcon.style.display = 'none';
  }
}

// ----- Toast notifications -----
function showToast(message, type = 'success', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach(el => {
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transition = 'opacity 0.5s';
      setTimeout(() => el.remove(), 500);
    }, 5000);
  });
});
