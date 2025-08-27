document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const videoFeed = document.getElementById('video-feed');
    const videoPlaceholder = document.getElementById('video-placeholder');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const logList = document.getElementById('log-list');
    const addStudentToggleBtn = document.getElementById('add-student-toggle-btn');
    const addStudentSection = document.getElementById('add-student-section');
    const addStudentForm = document.getElementById('add-student-form');
    const addStudentStatus = document.getElementById('add-student-status');
    const showStudentsBtn = document.getElementById('show-students-btn');
    const studentsListSection = document.getElementById('students-list-section');
    const studentsTableBody = document.getElementById('students-table-body');
    const menuButton = document.getElementById('menu-button');
    const dropdownMenu = document.getElementById('dropdown-menu');
    const themeToggle = document.getElementById('theme-toggle');
    const sunIcon = document.getElementById('sun-icon');
    const moonIcon = document.getElementById('moon-icon');

    // State Variables
    let isAttendanceRunning = false;
    let attendanceLog = {};

    // --- PWA Service Worker Registration ---
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/service-worker.js').then(registration => {
                console.log('Service Worker registered with scope:', registration.scope);
            }).catch(error => {
                console.log('Service Worker registration failed:', error);
            });
        });
    }

    // --- Utility Functions ---
    function showSection(sectionId) {
        const sections = [videoPlaceholder, addStudentSection, studentsListSection];
        sections.forEach(sec => {
            if (sec) sec.classList.add('hidden');
        });
        const targetSection = document.getElementById(sectionId);
        if (targetSection) targetSection.classList.remove('hidden');
    }

    function addLogEntry(message, type = 'info') {
        const li = document.createElement('li');
        li.className = `p-2 rounded-md ${type === 'success' ? 'bg-green-100 text-green-800' : type === 'warning' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'} dark:${type === 'success' ? 'bg-green-700 text-green-100' : type === 'warning' ? 'bg-yellow-700 text-yellow-100' : 'bg-gray-700 text-gray-100'}`;
        li.textContent = message;
        logList.prepend(li);
        if (logList.children.length > 5) {
            logList.lastChild.remove();
        }
    }

    function updateTheme() {
        if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
            sunIcon.classList.add('hidden');
            moonIcon.classList.remove('hidden');
        } else {
            document.documentElement.classList.remove('dark');
            sunIcon.classList.remove('hidden');
            moonIcon.classList.add('hidden');
        }
    }

    // --- Event Handlers ---
    startBtn.addEventListener('click', async () => {
        if (isAttendanceRunning) return;
        isAttendanceRunning = true;
        
        const response = await fetch('/api/start_attendance');
        const data = await response.json();
        
        if (data.status === 'success') {
            videoFeed.src = "/video_feed";
            videoFeed.onload = () => {
                videoPlaceholder.classList.add('hidden');
                videoFeed.classList.remove('hidden');
                addLogEntry("Attendance system started successfully.", 'success');
            };
        } else {
            addLogEntry(data.message, 'warning');
            isAttendanceRunning = false;
        }
    });

    stopBtn.addEventListener('click', async () => {
        if (!isAttendanceRunning) return;
        isAttendanceRunning = false;
        
        const response = await fetch('/api/stop_attendance');
        const data = await response.json();
        
        if (data.status === 'success') {
            videoFeed.src = "";
            videoFeed.classList.add('hidden');
            videoPlaceholder.classList.remove('hidden');
            addLogEntry("Attendance system stopped.", 'info');
        }
    });

    addStudentToggleBtn.addEventListener('click', () => {
        dropdownMenu.classList.add('hidden');
        showSection('add-student-section');
    });

    showStudentsBtn.addEventListener('click', async () => {
        dropdownMenu.classList.add('hidden');
        showSection('students-list-section');
        studentsTableBody.innerHTML = '';
        
        const response = await fetch('/api/students');
        const data = await response.json();

        if (data.status === 'success' && data.students.length > 0) {
            data.students.forEach(student => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td class="px-6 py-4 whitespace-nowrap">${student.registration_number}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${student.name}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${student.major}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${student.year}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${student.total_attendance}</td>
                `;
                studentsTableBody.appendChild(row);
            });
        } else {
            studentsTableBody.innerHTML = '<tr><td colspan="5" class="px-6 py-4 text-center text-gray-500">No students registered.</td></tr>';
        }
    });
    
    addStudentForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        addStudentStatus.textContent = 'Adding student...';
        addStudentStatus.className = 'text-center mt-2 text-blue-500';

        const formData = new FormData(addStudentForm);
        
        try {
            const response = await fetch('/api/add-student', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();
            
            if (response.ok) {
                addStudentStatus.textContent = result.message;
                addStudentStatus.className = 'text-center mt-2 text-green-600';
                addStudentForm.reset();
            } else {
                addStudentStatus.textContent = `Error: ${result.message}`;
                addStudentStatus.className = 'text-center mt-2 text-red-600';
            }
        } catch (error) {
            addStudentStatus.textContent = 'Network error or server issue.';
            addStudentStatus.className = 'text-center mt-2 text-red-600';
            console.error('Error:', error);
        }
    });

    menuButton.addEventListener('click', () => {
        dropdownMenu.classList.toggle('hidden');
    });

    document.addEventListener('click', (event) => {
        if (!menuButton.contains(event.target) && !dropdownMenu.contains(event.target)) {
            dropdownMenu.classList.add('hidden');
        }
    });

    themeToggle.addEventListener('click', () => {
        if (document.documentElement.classList.contains('dark')) {
            document.documentElement.classList.remove('dark');
            localStorage.theme = 'light';
        } else {
            document.documentElement.classList.add('dark');
            localStorage.theme = 'dark';
        }
        updateTheme();
    });

    // Initializations
    updateTheme();
    showSection('video-placeholder');

    // Real-time log updater (polling)
    setInterval(async () => {
        if (!isAttendanceRunning) return;
        try {
            const response = await fetch('/api/latest-attendance');
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success' && data.log && data.log.length > 0) {
                    data.log.forEach(entry => {
                        const logKey = `${entry.reg_no}-${entry.timestamp}`;
                        if (!attendanceLog[logKey]) {
                            addLogEntry(`✅ ${entry.name} (${entry.reg_no}) checked in at ${new Date(entry.timestamp).toLocaleTimeString()}`, 'success');
                            attendanceLog[logKey] = true;
                        }
                    });
                }
            }
        } catch (e) {
            console.error("Failed to fetch latest attendance log:", e);
        }
    }, 5000);
});