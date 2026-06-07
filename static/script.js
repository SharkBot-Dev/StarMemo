const SKY_WIDTH = 3000;
const SKY_HEIGHT = 3000;

const globalPosts = [];

const sky = document.getElementById('sky');
const scrollWrapper = document.getElementById('scroll-wrapper');
const canvas = document.getElementById('constellationCanvas');
const ctx = canvas.getContext('2d');
const memoInput = document.getElementById('memoInput');
const addMemoBtn = document.getElementById('addMemoBtn');
const searchInput = document.getElementById('searchInput');
const showPublicToggle = document.getElementById('showPublicToggle');

let stars = [];
let memoConnections = [];
let searchTimeout = null;
let currentZoom = 1.0;

const zoomContainer = document.getElementById('zoom-container');
const zoomInBtn = document.getElementById('zoomInBtn');
const zoomOutBtn = document.getElementById('zoomOutBtn');
const zoomLevelIndicator = document.getElementById('zoomLevelIndicator');

function setZoom(level) {
    currentZoom = Math.max(0.2, Math.min(3.0, level));
    zoomContainer.style.transform = `scale(${currentZoom})`;
    
    const scrollContent = document.getElementById('scroll-content');
    if (scrollContent) {
        scrollContent.style.width = (SKY_WIDTH * currentZoom) + 'px';
        scrollContent.style.height = (SKY_HEIGHT * currentZoom) + 'px';
    }
    
    zoomLevelIndicator.textContent = `${Math.round(currentZoom * 100)}%`;
}

zoomInBtn.addEventListener('click', () => setZoom(currentZoom + 0.1));
zoomOutBtn.addEventListener('click', () => setZoom(currentZoom - 0.1));

window.addEventListener('wheel', (e) => {
    if (e.ctrlKey) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.05 : 0.05;
        setZoom(currentZoom + delta);
    }
}, { passive: false });

// Prevent default browser zoom on iOS Safari and other gesture-supporting browsers
window.addEventListener('gesturestart', (e) => {
    e.preventDefault();
});
window.addEventListener('gesturechange', (e) => {
    e.preventDefault();
});

// Implement custom pinch-to-zoom for mobile touch devices
let touchStartDist = 0;
let initialZoom = 1.0;

window.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        touchStartDist = Math.sqrt(dx * dx + dy * dy);
        initialZoom = currentZoom;
    }
}, { passive: true });

window.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2) {
        e.preventDefault(); // Prevents browser default zoom
        if (touchStartDist > 0) {
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const factor = dist / touchStartDist;
            setZoom(initialZoom * factor);
        }
    }
}, { passive: false });

window.addEventListener('touchend', (e) => {
    if (e.touches.length < 2) {
        touchStartDist = 0;
    }
});

async function fetchMemos(query = '') {
    try {
        const url = query ? `/api/memos?q=${encodeURIComponent(query)}` : '/api/memos';
        const response = await fetch(url);
        return await response.json();
    } catch (e) {
        console.error("Failed to fetch memos", e);
        return { memos: [], connections: [] };
    }
}

async function addMemo() {
    const text = memoInput.value.trim();
    if (!text) return;
    const isPublic = document.getElementById('isPublicCheckbox').checked;

    try {
        const response = await fetch('/api/memos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, is_public: isPublic })
        });
        if (response.ok) {
            memoInput.value = '';
            memoInput.style.height = 'auto'; 
            searchInput.value = '';
            initConstellation(true);
        }
    } catch (e) {
        console.error("Failed to add memo", e);
    }
}

addMemoBtn.addEventListener('click', addMemo);
memoInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        addMemo();
    }
});

memoInput.addEventListener('input', () => {
    memoInput.style.height = 'auto';
    memoInput.style.height = (memoInput.scrollHeight) + 'px';
});

searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        initConstellation();
    }, 500);
});

showPublicToggle.addEventListener('change', () => {
    initConstellation();
});

function resizeCanvas() {
    canvas.width = SKY_WIDTH;
    canvas.height = SKY_HEIGHT;
    initConstellation();
}

// Deterministic helper functions for positioning
function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = (hash << 5) - hash + char;
        hash |= 0; // Convert to 32bit integer
    }
    return hash;
}

function getDeterministicRandom(seed) {
    const hash = hashCode(seed);
    const x = Math.sin(hash) * 10000;
    return x - Math.floor(x);
}

async function initConstellation(scrollToLatest = false) {
    sky.innerHTML = '';
    stars = [];

    const query = searchInput.value.trim();
    const data = await fetchMemos(query);
    let allPosts = data.memos || [];
    
    const currentUsername = document.getElementById('currentUsername').value;
    const showPublic = showPublicToggle.checked;

    if (!showPublic) {
        allPosts = allPosts.filter(p => p.username === currentUsername);
    }

    // Re-calculate connections for the filtered set
    memoConnections = [];
    for (let i = 0; i < allPosts.length; i++) {
        for (let j = i + 1; j < allPosts.length; j++) {
            const keywords1 = new Set(allPosts[i].keywords);
            const keywords2 = new Set(allPosts[j].keywords);
            const intersection = [...keywords1].filter(k => keywords2.has(k));
            if (intersection.length > 0) {
                memoConnections.push([i, j]);
            }
        }
    }

    const margin = 200;
    let latestStarPos = null;

    let totalX = 0;
    let totalY = 0;

    const createStar = (post) => {
        const isMine = post.username === currentUsername;

        // Determine deterministic positions based on keywords and post ID to cluster them
        let mainKeyword = null;
        if (post.keywords && post.keywords.length > 0) {
            const sortedKeywords = [...post.keywords].sort();
            mainKeyword = sortedKeywords[0];
        }

        const clusterMargin = margin + 150;
        const clusterWidth = SKY_WIDTH - clusterMargin * 2;
        const clusterHeight = SKY_HEIGHT - clusterMargin * 2;

        let clusterX, clusterY;
        if (mainKeyword) {
            clusterX = clusterMargin + getDeterministicRandom(mainKeyword + "-x") * clusterWidth;
            clusterY = clusterMargin + getDeterministicRandom(mainKeyword + "-y") * clusterHeight;
        } else {
            // No keywords: distribute using post ID
            clusterX = clusterMargin + getDeterministicRandom(post._id + "-default-x") * clusterWidth;
            clusterY = clusterMargin + getDeterministicRandom(post._id + "-default-y") * clusterHeight;
        }

        let x, y;
        const offsetRadius = 180; // Radius for the cluster spreading
        if (mainKeyword) {
            const angle = getDeterministicRandom(post._id + "-angle") * 2 * Math.PI;
            const distance = getDeterministicRandom(post._id + "-dist") * offsetRadius;
            x = clusterX + Math.cos(angle) * distance;
            y = clusterY + Math.sin(angle) * distance;
        } else {
            x = clusterX;
            y = clusterY;
        }

        // Clamp values to ensure stars stay within safe bounds
        x = Math.max(margin, Math.min(SKY_WIDTH - margin, x));
        y = Math.max(margin, Math.min(SKY_HEIGHT - margin, y));

        totalX += x;
        totalY += y;
        
        const starNode = document.createElement('div');
        starNode.className = 'star-node' + (isMine ? ' private' : ' public');
        starNode.style.left = `${x}px`;
        starNode.style.top = `${y}px`;

        const bubble = document.createElement('div');
        bubble.className = 'post-bubble';
        
        if (!isMine) {
            const author = document.createElement('div');
            author.className = 'author-name';
            author.textContent = `@${post.username}`;
            bubble.appendChild(author);
        }
        
        const textContent = document.createElement('div');
        textContent.textContent = post.text;
        bubble.appendChild(textContent);

        const preview = document.createElement('div');
        preview.className = 'post-preview';
        preview.innerText = post.text.length > 20 ? post.text.substring(0, 20) + '...' : post.text;

        starNode.appendChild(bubble);
        starNode.appendChild(preview);
        sky.appendChild(starNode);

        starNode.addEventListener('click', (e) => {
            const isActive = starNode.classList.contains('active');
            document.querySelectorAll('.star-node').forEach(s => s.classList.remove('active'));
            if (!isActive) {
                starNode.classList.add('active');
            }
            e.stopPropagation();
        });

        stars.push({ x, y, isMine, element: starNode });
        return { x, y };
    };

    allPosts.forEach((post, index) => {
        const pos = createStar(post);
        if (scrollToLatest && index === allPosts.length - 1 && post.username === currentUsername) {
            latestStarPos = pos;
        }
    });

    if (latestStarPos) {
        scrollWrapper.scrollTo({
            left: (latestStarPos.x * currentZoom) - window.innerWidth / 2,
            top: (latestStarPos.y * currentZoom) - window.innerHeight / 2,
            behavior: 'smooth'
        });
    } else if (allPosts.length > 0) {
        scrollWrapper.scrollTo({
            left: ((totalX / allPosts.length) * currentZoom) - window.innerWidth / 2,
            top: ((totalY / allPosts.length) * currentZoom) - window.innerHeight / 2,
            behavior: 'smooth'
        });
    }

    document.addEventListener('click', () => {
        document.querySelectorAll('.star-node').forEach(s => s.classList.remove('active'));
    });

    for (let i = 0; i < 300; i++) {
        const bgStar = document.createElement('div');
        bgStar.className = 'bg-star';
        const sizeSeed = getDeterministicRandom(`bg-size-${i}`);
        const size = sizeSeed * 2 + 1; // Size between 1px and 3px
        bgStar.style.width = `${size}px`;
        bgStar.style.height = `${size}px`;
        bgStar.style.left = `${getDeterministicRandom(`bg-x-${i}`) * SKY_WIDTH}px`;
        bgStar.style.top = `${getDeterministicRandom(`bg-y-${i}`) * SKY_HEIGHT}px`;
        sky.appendChild(bgStar);
    }

    drawLines();
}

function drawLines() {
    if (stars.length === 0) return;
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1.0;
    
    memoConnections.forEach(([i, j]) => {
        if (stars[i] && stars[j]) {
            ctx.beginPath();
            ctx.moveTo(stars[i].x, stars[i].y);
            ctx.lineTo(stars[j].x, stars[j].y);
            ctx.stroke();
        }
    });
}

window.addEventListener('resize', resizeCanvas);

function updateSkyColor() {
    const now = new Date();
    const t = now.getHours() + now.getMinutes() / 60 + now.getSeconds() / 3600;

    const skyColors = [
        { hour: 0,  c1: [2, 0, 16],   c2: [5, 4, 21],   c3: [10, 8, 36] },     // 深夜
        { hour: 4,  c1: [15, 12, 27], c2: [44, 27, 77], c3: [90, 40, 70] },    // 明け初め
        { hour: 6,  c1: [20, 30, 80], c2: [120, 60, 100], c3: [255, 126, 95] }, // 朝焼け
        { hour: 8,  c1: [26, 42, 108],c2: [39, 83, 167],c3: [56, 163, 165] },  // 午前
        { hour: 12, c1: [10, 80, 180],c2: [30, 130, 210],c3: [100, 200, 230] }, // 真昼
        { hour: 16, c1: [26, 15, 48], c2: [168, 50, 121],c3: [255, 126, 95] },  // 夕方
        { hour: 18, c1: [15, 10, 35], c2: [80, 30, 90],  c3: [180, 70, 70] },   // 日没直後
        { hour: 20, c1: [5, 3, 20],   c2: [15, 10, 45],  c3: [40, 25, 75] },    // 宵のうち
        { hour: 24, c1: [2, 0, 16],   c2: [5, 4, 21],   c3: [10, 8, 36] }      // 深夜
    ];

    let start = skyColors[0];
    let end = skyColors[skyColors.length - 1];

    for (let i = 0; i < skyColors.length - 1; i++) {
        if (t >= skyColors[i].hour && t < skyColors[i+1].hour) {
            start = skyColors[i];
            end = skyColors[i+1];
            break;
        }
    }

    const range = end.hour - start.hour;
    const ratio = (t - start.hour) / range;

    const lerp = (a, b, r) => Math.round(a * (1 - r) + b * r);
    const lerpColor = (cStart, cEnd, r) => {
        return `rgb(${lerp(cStart[0], cEnd[0], r)}, ${lerp(cStart[1], cEnd[1], r)}, ${lerp(cStart[2], cEnd[2], r)})`;
    };

    const color1 = lerpColor(start.c1, end.c1, ratio);
    const color2 = lerpColor(start.c2, end.c2, ratio);
    const color3 = lerpColor(start.c3, end.c3, ratio);

    document.documentElement.style.setProperty('--sky-color-1', color1);
    document.documentElement.style.setProperty('--sky-color-2', color2);
    document.documentElement.style.setProperty('--sky-color-3', color3);
}

// 1分ごとに背景色を更新
setInterval(updateSkyColor, 60000);

window.addEventListener('DOMContentLoaded', () => {
    updateSkyColor();
    initClouds();
    resizeCanvas();
    scrollWrapper.scrollTo({
        left: (SKY_WIDTH * currentZoom - window.innerWidth) / 2,
        top: (SKY_HEIGHT * currentZoom - window.innerHeight) / 2,
        behavior: 'instant'
    });
});

// GUI表示・非表示のトグルロジック
const toggleGuiBtn = document.getElementById('toggle-gui-btn');

function toggleGUI() {
    document.body.classList.toggle('gui-hidden');
    const isHidden = document.body.classList.contains('gui-hidden');
    localStorage.setItem('gui-hidden', isHidden);
}

if (toggleGuiBtn) {
    toggleGuiBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleGUI();
    });
}

// 初期状態の復元
if (localStorage.getItem('gui-hidden') === 'true') {
    document.body.classList.add('gui-hidden');
}

// キーボードショートカット (Hキーでトグル)
window.addEventListener('keydown', (e) => {
    // アクティブな要素が入力フィールド（textareaやinput）の場合はショートカットを無視
    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
        return;
    }
    
    // 'h' または 'H' キー
    if (e.key === 'h' || e.key === 'H') {
        e.preventDefault();
        toggleGUI();
    }
});

// 最もメモが密集しているエリアを探索する関数
function findDensestArea() {
    if (stars.length === 0) return null;
    
    const radius = 300; // 密集度を判定する半径（ピクセル）
    let maxCount = -1;
    let bestStar = null;
    
    for (let i = 0; i < stars.length; i++) {
        let count = 0;
        const s1 = stars[i];
        for (let j = 0; j < stars.length; j++) {
            const s2 = stars[j];
            const distSq = (s1.x - s2.x) ** 2 + (s1.y - s2.y) ** 2;
            if (distSq <= radius * radius) {
                count++;
            }
        }
        if (count > maxCount) {
            maxCount = count;
            bestStar = s1;
        }
    }
    
    return bestStar;
}

// 密集エリアへ移動する関数
function scrollToDensestArea() {
    const target = findDensestArea();
    if (target) {
        scrollWrapper.scrollTo({
            left: (target.x * currentZoom) - window.innerWidth / 2,
            top: (target.y * currentZoom) - window.innerHeight / 2,
            behavior: 'smooth'
        });
        
        // 既存のアクティブな星をクリアし、密集地の中心の星をアクティブにしてポップアップを表示する
        document.querySelectorAll('.star-node').forEach(s => s.classList.remove('active'));
        if (target.element) {
            target.element.classList.add('active');
        }
    }
}

// 最も密集しているエリアへの移動ボタンのイベントリスナー設定
const goToDensestBtn = document.getElementById('goToDensestBtn');
if (goToDensestBtn) {
    goToDensestBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        scrollToDensestArea();
    });
}

// PC版でのドラッグスクロールの実装
let isDragging = false;
let startX = 0;
let startY = 0;
let scrollLeftStart = 0;
let scrollTopStart = 0;
let hasMoved = false;
let preventNextClick = false;

scrollWrapper.addEventListener('mousedown', (e) => {
    // 左クリックのみドラッグを開始
    if (e.button !== 0) return;
    
    // スクロールバー上でのクリック時はドラッグを開始しない
    const rect = scrollWrapper.getBoundingClientRect();
    const isInScrollbar = (e.clientX >= rect.left + scrollWrapper.clientWidth) ||
                          (e.clientY >= rect.top + scrollWrapper.clientHeight);
    if (isInScrollbar) return;
    
    isDragging = true;
    hasMoved = false;
    preventNextClick = false;
    
    startX = e.clientX;
    startY = e.clientY;
    scrollLeftStart = scrollWrapper.scrollLeft;
    scrollTopStart = scrollWrapper.scrollTop;
    
    scrollWrapper.classList.add('is-dragging');
});

window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    
    // わずかな動き（5px以上）をドラッグスクロールとみなす
    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
        hasMoved = true;
        preventNextClick = true;
    }
    
    scrollWrapper.scrollLeft = scrollLeftStart - dx;
    scrollWrapper.scrollTop = scrollTopStart - dy;
});

window.addEventListener('mouseup', () => {
    if (!isDragging) return;
    isDragging = false;
    scrollWrapper.classList.remove('is-dragging');
});

// ドラッグ移動した後のクリックイベントをインターセプトしてキャンセルする
scrollWrapper.addEventListener('click', (e) => {
    if (preventNextClick) {
        e.stopPropagation();
        e.preventDefault();
        preventNextClick = false;
    }
}, true);

// Clouds Spawning and Animation Logic
const cloudsContainer = document.getElementById('clouds');

function spawnCloud(initial = false) {
    if (!cloudsContainer) return;

    const cloud = document.createElement('div');
    cloud.className = 'cloud';

    const width = Math.random() * 400 + 300; // 300px - 700px
    const height = Math.random() * 150 + 100; // 100px - 250px
    const top = Math.random() * (SKY_HEIGHT - height);
    const opacity = Math.random() * 0.05 + 0.04; // 0.04 - 0.09
    const duration = Math.random() * 120 + 120; // 120s - 240s

    cloud.style.width = `${width}px`;
    cloud.style.height = `${height}px`;
    cloud.style.top = `${top}px`;
    cloud.style.opacity = opacity;
    cloud.style.animationName = 'moveCloud';
    cloud.style.animationDuration = `${duration}s`;

    if (initial) {
        // Initial setup: place clouds at random positions on screen to start with
        const startX = Math.random() * (SKY_WIDTH + 800) - 800;
        cloud.style.left = `${startX}px`;
        
        // Calculate negative delay to keep the animation progressing from the startX position
        const totalDistance = SKY_WIDTH + 1600; // -800 to 3800 is 4600px
        const currentDistance = startX + 800;
        const progress = currentDistance / totalDistance;
        const delay = -progress * duration;
        cloud.style.animationDelay = `${delay}s`;
    }

    cloudsContainer.appendChild(cloud);

    // Remove the cloud element once its animation ends
    cloud.addEventListener('animationend', () => {
        cloud.remove();
    });
}

function initClouds() {
    if (!cloudsContainer) return;

    // Initially spawn 5-8 clouds distributed randomly across the sky
    const initialCloudCount = Math.floor(Math.random() * 4) + 5; // 5 to 8
    for (let i = 0; i < initialCloudCount; i++) {
        spawnCloud(true);
    }

    // Periodically spawn a new cloud from the left side (every 25-45 seconds)
    setInterval(() => {
        // Keep maximum cloud count to 12 to maintain subtle look
        if (cloudsContainer.children.length < 12) {
            spawnCloud(false);
        }
    }, Math.random() * 20000 + 25000);
}

