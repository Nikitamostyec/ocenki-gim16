const STORAGE_KEY = 'ocenki_gim16_v1';

let state = {
    students: [],
    history: [],
    ee: { enabled: false, threshold: 4, message: 'Нужно подтянуть!' }
};

let pendingImport = [];

const gridEl = document.getElementById('cardsGrid');
const undoBtn = document.getElementById('undoBtn');
const resetBtn = document.getElementById('resetBtn');
const exportBtn = document.getElementById('exportBtn');
const fileInput = document.getElementById('fileInput');
const eeEnabled = document.getElementById('eeEnabled');
const eeThreshold = document.getElementById('eeThreshold');
const eeMessage = document.getElementById('eeMessage');
const previewModal = document.getElementById('previewModal');
const previewList = document.getElementById('previewList');
const previewCount = document.getElementById('previewCount');

function init() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
        try {
            state = JSON.parse(saved);
        } catch (e) {}
    }
    eeEnabled.checked = state.ee.enabled;
    eeThreshold.value = state.ee.threshold;
    eeMessage.value = state.ee.message;
    render();
}

function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function pushHistory() {
    state.history.push(JSON.stringify(state.students));
    if (state.history.length > 50) state.history.shift();
}

function getGrade(student) {
    if (!student.touched || student.points === 0) return '';
    if (student.points === 1) return 2;
    return Math.min(student.points, 10);
}

function getEasterEggNote(student) {
    if (!state.ee.enabled) return '';
    const grade = getGrade(student);
    if (grade !== '' && grade < Number(state.ee.threshold)) {
        return state.ee.message;
    }
    return '';
}

function handleCardClick(id) {
    const idx = state.students.findIndex(s => s.id === id);
    if (idx === -1) return;
    pushHistory();
    const s = state.students[idx];
    s.touched = true;
    if (s.points < 10) s.points += 1;
    saveState();
    render();
}

function render() {
    undoBtn.disabled = state.history.length === 0;
    gridEl.innerHTML = '';

    state.students.forEach(s => {
        const grade = getGrade(s);
        const eeNote = getEasterEggNote(s);
        const card = document.createElement('div');
        card.className = 'student-card' + (s.touched ? (s.points >= 10 ? ' maxed' : ' active') : '');
        card.onclick = () => handleCardClick(s.id);

        card.innerHTML = `
            <div class="student-name">${escapeHtml(s.name)}</div>
            <div class="student-score-row">
                <span class="student-grade">${grade !== '' ? grade : '—'}</span>
                <span class="student-points">(${s.points} б.)</span>
            </div>
            <div class="student-ee">${escapeHtml(eeNote)}</div>
        `;
        gridEl.appendChild(card);
    });
}

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[m]));
}

undoBtn.onclick = () => {
    if (!state.history.length) return;
    state.students = JSON.parse(state.history.pop());
    saveState();
    render();
};

resetBtn.onclick = () => {
    if (!state.students.length) return;
    pushHistory();
    state.students.forEach(s => {
        s.points = 0;
        s.touched = false;
    });
    saveState();
    render();
};

[eeEnabled, eeThreshold, eeMessage].forEach(el => {
    el.addEventListener('input', () => {
        state.ee.enabled = eeEnabled.checked;
        state.ee.threshold = Number(eeThreshold.value) || 4;
        state.ee.message = eeMessage.value;
        saveState();
        render();
    });
});

fileInput.onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/import/', { method: 'POST', body: formData });
        const result = await res.json();
        if (!res.ok) {
            alert(result.error || 'Ошибка импорта');
            return;
        }
        pendingImport = result.names || [];
        if (!pendingImport.length) {
            alert('В файле не найдены строки с ФИО учеников.');
        } else {
            showPreview(pendingImport);
        }
    } catch (err) {
        alert('Ошибка соединения при чтении файла: ' + err.message);
    } finally {
        fileInput.value = '';
    }
};

function showPreview(names) {
    previewCount.textContent = names.length;
    previewList.innerHTML = names.map(n => `<li>${escapeHtml(n)}</li>`).join('');
    previewModal.classList.remove('hidden');
}

document.getElementById('confirmImportBtn').onclick = () => {
    state.students = pendingImport.map((name, i) => ({
        id: i + 1,
        name,
        points: 0,
        touched: false
    }));
    state.history = [];
    saveState();
    render();
    previewModal.classList.add('hidden');
};

document.getElementById('cancelImportBtn').onclick = () => {
    previewModal.classList.add('hidden');
};

exportBtn.onclick = async () => {
    const anyTouched = state.students.some(s => s.touched);
    const rows = [['№', 'ФИО', 'Баллы', 'Итоговая оценка', 'Комментарий']];

    state.students.forEach((s, idx) => {
        if (!anyTouched || !s.touched) {
            rows.push([idx + 1, s.name, '', '', '']);
        } else {
            rows.push([idx + 1, s.name, s.points, getGrade(s), getEasterEggNote(s)]);
        }
    });

    const res = await fetch('/api/export/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows })
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Ocenki_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
};

init();
