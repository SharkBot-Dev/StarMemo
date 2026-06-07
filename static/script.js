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
            memoInput.style.height = 'auto'; // Reset height
            document.getElementById('isPublicCheckbox').checked = false;
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
        const x = Math.random() * (SKY_WIDTH - margin * 2) + margin;
        const y = Math.random() * (SKY_HEIGHT - margin * 2) + margin;

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

        stars.push({ x, y, isMine });
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
            left: latestStarPos.x - window.innerWidth / 2,
            top: latestStarPos.y - window.innerHeight / 2,
            behavior: 'smooth'
        });
    } else if (allPosts.length > 0) {
        scrollWrapper.scrollTo({
            left: (totalX / allPosts.length) - window.innerWidth / 2,
            top: (totalY / allPosts.length) - window.innerHeight / 2,
            behavior: 'smooth'
        });
    }

    document.addEventListener('click', () => {
        document.querySelectorAll('.star-node').forEach(s => s.classList.remove('active'));
    });

    for (let i = 0; i < 300; i++) {
        const bgStar = document.createElement('div');
        bgStar.className = 'bg-star';
        bgStar.style.width = `${Math.random() * 3}px`;
        bgStar.style.height = bgStar.style.width;
        bgStar.style.left = `${Math.random() * SKY_WIDTH}px`;
        bgStar.style.top = `${Math.random() * SKY_HEIGHT}px`;
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
window.addEventListener('DOMContentLoaded', () => {
    resizeCanvas();
    scrollWrapper.scrollTo({
        left: (SKY_WIDTH - window.innerWidth) / 2,
        top: (SKY_HEIGHT - window.innerHeight) / 2,
        behavior: 'instant'
    });
});
