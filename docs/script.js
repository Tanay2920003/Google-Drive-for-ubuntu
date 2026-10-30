/**
 * Google Drive for Linux (GDriveSync) - GitHub Pages Interactive Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
  setupNavbarScroll();
  setupCopyButton();
  setupKeyboardShortcuts();
});

// 1. Navbar Sticky Shadow on Scroll
function setupNavbarScroll() {
  const navbar = document.getElementById('navbar');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 20) {
      navbar.style.background = 'rgba(18, 19, 22, 0.95)';
      navbar.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.4)';
    } else {
      navbar.style.background = 'rgba(18, 19, 22, 0.85)';
      navbar.style.boxShadow = 'none';
    }
  });
}

// 2. One-click Copy Button for Install Command
function setupCopyButton() {
  const copyBtn = document.getElementById('hero-copy-btn');
  const cmdText = document.getElementById('cmd-text');

  if (copyBtn && cmdText) {
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(cmdText.textContent.trim());
        copyBtn.classList.add('copied');
        copyBtn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          Copied!
        `;
        setTimeout(() => {
          copyBtn.classList.remove('copied');
          copyBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            Copy
          `;
        }, 2200);
      } catch (err) {
        console.error('Failed to copy text: ', err);
      }
    });
  }
}

// 3. Interactive Sync Mode Comparator
const modeData = {
  stream: {
    title: 'Stream Files (Virtual FUSE Mount)',
    desc: 'Store all files in the cloud only. Browse your entire multi-terabyte Google Drive through <code>~/GoogleDrive</code> with zero local disk footprint. Files stream transparently on-demand as you open them.',
    bullets: [
      'Saves local hard drive space (perfect for laptops and SSDs).',
      'Files open and cache automatically in temporary VFS storage.',
      'Any local edits sync back to Google Drive upon save.'
    ],
    disk: '~0 MB (On-Demand)',
    offline: 'Cached files only',
    path: '~/GoogleDrive',
    engine: 'FUSE3 VFS Cache'
  },
  mirror: {
    title: 'Mirror Files (Two-Way Offline Sync)',
    desc: 'Store files both in the cloud and on your local disk. All folders and documents are synced to <code>~/GoogleDrive_Mirror</code>, making them available 100% offline anytime.',
    bullets: [
      '100% offline access to all your files, documents, and vaults.',
      'Instant local read and write speeds directly on disk.',
      'Real-time inotify file system watcher uploads changes in milliseconds.'
    ],
    disk: '100% Full Local Copy',
    offline: 'All files 100% offline',
    path: '~/GoogleDrive_Mirror',
    engine: 'Inotify Bi-directional Sync'
  }
};

function switchSyncMode(mode) {
  const data = modeData[mode];
  if (!data) return;

  document.getElementById('tab-stream').classList.toggle('active', mode === 'stream');
  document.getElementById('tab-mirror').classList.toggle('active', mode === 'mirror');

  document.getElementById('mode-title').innerHTML = data.title;
  document.getElementById('mode-desc').innerHTML = data.desc;
  
  const bulletsEl = document.getElementById('mode-bullets');
  bulletsEl.innerHTML = data.bullets.map(b => `<li>${b}</li>`).join('');

  document.getElementById('stat-disk').textContent = data.disk;
  document.getElementById('stat-offline').textContent = data.offline;
  document.getElementById('stat-path').textContent = data.path;
  document.getElementById('stat-engine').textContent = data.engine;
}

// 4. Interactive Other Computers Virtual Drive Tree Explorer
const treeData = {
  root: {
    title: 'GoogleDrive (Root Virtual Drive)',
    desc: 'The top-level mounted virtual drive combining both your personal "My Drive" and all backed-up computers in one unified file system tree.'
  },
  mydrive: {
    title: 'My Drive /',
    desc: 'Your standard personal Google Drive files, shared files, and Google Docs, perfectly synced and searchable.'
  },
  other_comp: {
    title: 'Other computers /',
    desc: 'Matching Windows G:\\Other computers\\ layout. Contains dedicated subfolders for each of your linked laptops and PCs.'
  },
  laptop: {
    title: 'LAPTOP (My Laptop)',
    desc: 'Linked computer ID "comp_sample" mapped to Google Drive folder "1AbC2dEf3GhIjKlMnOpQrStUvWxYz".'
  },
  obsidian: {
    title: 'OBSIDIAN Vault',
    desc: 'User markdown notes vault synced directly between Linux and laptop. Includes notes, canvases, and attachments.'
  },
  file1: {
    title: 'Roadmap_2026.md',
    desc: 'Markdown file in OBSIDIAN vault. Size: 47 KB. Opens instantly with on-demand chunk streaming.'
  },
  file2: {
    title: 'Project_Demo.mp4',
    desc: 'Video asset stored in cloud. Size: 23.4 MB. Streams smoothly without consuming permanent local storage.'
  }
};

function selectTreeNode(key) {
  const nodes = document.querySelectorAll('.tree-node');
  nodes.forEach(n => n.classList.remove('selected'));
  
  const item = treeData[key];
  if (item) {
    document.getElementById('tree-info-title').textContent = item.title;
    document.getElementById('tree-info-desc').innerHTML = item.desc;
  }
}

// 5. Screenshots Gallery Switcher
const galleryImages = {
  main: 'assets/screenshots/main_window.png',
  sync: 'assets/screenshots/preferences_sync_mode.png',
  comp: 'assets/screenshots/preferences_computers.png',
  settings: 'assets/screenshots/preferences_settings.png'
};

function switchGallery(key) {
  const tabs = document.querySelectorAll('.gallery-tab-btn');
  tabs.forEach(t => t.classList.remove('active'));
  
  // Highlight clicked tab
  if (event && event.target) {
    event.target.classList.add('active');
  }

  const img = document.getElementById('gallery-img');
  const targetSrc = galleryImages[key];
  if (img && targetSrc) {
    img.style.opacity = '0.3';
    setTimeout(() => {
      img.src = targetSrc;
      img.style.opacity = '1';
    }, 150);
  }
}

// 6. Lightbox Modal for Zooming Screenshots
function openLightbox() {
  const currentImg = document.getElementById('gallery-img');
  const modal = document.getElementById('lightbox');
  const modalImg = document.getElementById('lightbox-img');
  if (currentImg && modal && modalImg) {
    modalImg.src = currentImg.src;
    modal.classList.add('active');
  }
}

function closeLightbox(e) {
  if (e.target.id === 'lightbox' || e.target.classList.contains('lightbox-close')) {
    document.getElementById('lightbox').classList.remove('active');
  }
}

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const modal = document.getElementById('lightbox');
      if (modal && modal.classList.contains('active')) {
        modal.classList.remove('active');
      }
    }
  });
}

// 7. Terminal Installation Tabs Switcher
const installTabsData = {
  oneclick: {
    title: 'bash - install.sh (Automated)',
    content: `
      <div class="terminal-comment"># 1. Clone the repository</div>
      <code>git clone https://github.com/developertan/GDRIVSYNC.git</code><br>
      <code>cd GDRIVSYNC</code><br><br>
      <div class="terminal-comment"># 2. Run the automated installer (installs icons, launcher, and autostart)</div>
      <code>chmod +x install.sh run.sh</code><br>
      <code>./install.sh</code><br><br>
      <div class="terminal-comment"># 3. Launch from GNOME Activities or terminal:</div>
      <code>./run.sh</code>
    `
  },
  manual: {
    title: 'bash - run.sh (Manual / Background)',
    content: `
      <div class="terminal-comment"># Launch GUI window directly:</div>
      <code>./run.sh</code><br><br>
      <div class="terminal-comment"># Start silently in background on boot (no window opened):</div>
      <code>./run.sh --hidden</code><br><br>
      <div class="terminal-comment"># Launch via system application launcher:</div>
      <code>gtk-launch google-drive</code>
    `
  },
  deps: {
    title: 'bash - Ubuntu / Debian Dependencies',
    content: `
      <div class="terminal-comment"># Install GTK 4, Libadwaita, FUSE3, and Python bindings:</div>
      <code>sudo apt update</code><br>
      <code>sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 fuse3 curl unzip</code><br><br>
      <div class="terminal-comment"># Compatible with Ubuntu 22.04 LTS, 24.04 LTS, 26.04, and modern GNOME systems.</div>
    `
  }
};

function switchInstallTab(tab) {
  const btns = document.querySelectorAll('.install-tab-btn');
  btns.forEach(b => b.classList.remove('active'));
  
  if (event && event.target) {
    event.target.classList.add('active');
  }

  const data = installTabsData[tab];
  if (data) {
    document.getElementById('term-title').textContent = data.title;
    document.getElementById('term-content').innerHTML = data.content;
  }
}

// 8. FAQ Accordion Toggle
function toggleFaq(btn) {
  const item = btn.parentElement;
  item.classList.toggle('active');
}
