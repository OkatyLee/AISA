// Telegram Mini App API с проверкой доступности
const tg = window.Telegram?.WebApp || {
    // Fallback объект для работы без Telegram
    expand: () => {},
    MainButton: {
        setText: () => {},
        onClick: () => {},
        show: () => {},
        hide: () => {}
    },
    HapticFeedback: {
        impactOccurred: () => {},
        notificationOccurred: () => {}
    },
    showAlert: (message) => alert(message),
    showPopup: (params, callback) => {
        const result = confirm(params.message);
        if (callback) callback(result ? 'ok' : 'cancel');
    },
    openLink: (url) => window.open(url, '_blank'),
    onEvent: () => {},
    colorScheme: 'light',
    themeParams: {
        bg_color: '#ffffff',
        text_color: '#000000',
        hint_color: '#999999',
        secondary_bg_color: '#f1f1f1'
    },
    initData: '',
    initDataUnsafe: { user: null }
};

// Ранняя инициализация темы до загрузки DOM
(function earlyThemeInit() {
    console.log('Early theme initialization (before DOM)...');
    
    const root = document.documentElement;
    const tgObj = window.Telegram?.WebApp;
    
    if (tgObj && tgObj.themeParams) {
        const themeParams = tgObj.themeParams;
        const isDark = tgObj.colorScheme === 'dark';
        
        console.log('Applying early Telegram theme:', { isDark, themeParams });
        
        // Применяем основные цвета сразу
        if (themeParams.bg_color) {
            root.style.setProperty('--tg-theme-bg-color', themeParams.bg_color);
            document.body.style.backgroundColor = themeParams.bg_color;
        }
        if (themeParams.text_color) {
            root.style.setProperty('--tg-theme-text-color', themeParams.text_color);
            document.body.style.color = themeParams.text_color;
        }
        if (themeParams.secondary_bg_color) {
            root.style.setProperty('--tg-theme-secondary-bg-color', themeParams.secondary_bg_color);
        }
        if (themeParams.button_color) {
            root.style.setProperty('--tg-theme-button-color', themeParams.button_color);
            root.style.setProperty('--primary-color', themeParams.button_color);
        }
        if (themeParams.hint_color) {
            root.style.setProperty('--tg-theme-hint-color', themeParams.hint_color);
        }
        
        // Добавляем класс темы к body как можно раньше
        if (document.body) {
            document.body.classList.toggle('dark-theme', isDark);
            document.body.classList.toggle('light-theme', !isDark);
        } else {
            // Если body еще не готов, добавляем через observer
            const observer = new MutationObserver((mutations) => {
                if (document.body) {
                    document.body.classList.toggle('dark-theme', isDark);
                    document.body.classList.toggle('light-theme', !isDark);
                    observer.disconnect();
                }
            });
            observer.observe(document, { childList: true, subtree: true });
        }
        
        console.log('Early Telegram theme applied successfully');
    } else {
        console.log('No Telegram theme available, using fallback');
    }
})();

class ScientificAssistantApp {
    constructor() {
        // Состояние приложения
        this.currentTab = 'library';
        this.currentPage = 1;
        this.perPage = 10;
        this.totalPapers = 0;
        this.allPapers = [];
        this.filteredPapers = [];
        this.currentPaper = null;
        this.chatHistory = [];
        
        this.initializeApp();
        this.initializeUI();
        this.initializeNavigation();
        this.bindEvents();
        this.loadLibrary();
    }
    
    // Вспомогательная функция для haptic feedback
    haptic(type, style = 'light') {
        try {
            if (type === 'impact') {
                tg.HapticFeedback.impactOccurred(style);
            } else if (type === 'notification') {
                tg.HapticFeedback.notificationOccurred(style);
            }
        } catch (e) {
            console.log('Haptic feedback not available:', type, style);
        }
    }
    
    // Отладка состояния вкладок
    debugTabState() {
        console.log('=== TAB DEBUG INFO ===');
        console.log('Current tab:', this.currentTab);
        
        document.querySelectorAll('.sa-nav-btn').forEach(btn => {
            console.log(`Button [${btn.dataset.tab}]:`, {
                active: btn.classList.contains('active'),
                visible: !btn.classList.contains('hidden')
            });
        });
        
        document.querySelectorAll('.sa-tab-content').forEach(tab => {
            console.log(`Tab [${tab.id}]:`, {
                active: tab.classList.contains('active'),
                computedDisplay: getComputedStyle(tab).display,
                computedVisibility: getComputedStyle(tab).visibility,
                computedOpacity: getComputedStyle(tab).opacity
            });
        });
        console.log('===================');
    }
    
    initializeApp() {
        console.log('Initializing app...', { hasTelegram: !!window.Telegram?.WebApp });
        
        // Расширяем Mini App на весь экран (если доступно)
        try {
            tg.expand();
        } catch (e) {
            console.log('Expand not available:', e);
        }
        
        // Устанавливаем тему с улучшенной поддержкой
        this.setupTheme();
        this.initializeThemeWatcher();
        
        // Подписываемся на изменения темы (если доступно)
        try {
            tg.onEvent('themeChanged', () => {
                console.log('Theme changed event received');
                this.setupTheme();
            });
        } catch (e) {
            console.log('Theme events not available:', e);
        }
        
        // Настраиваем главную кнопку (если доступно)
        try {
            tg.MainButton.setText('Обновить');
            tg.MainButton.onClick(() => this.refreshCurrentTab());
            tg.MainButton.show();
        } catch (e) {
            console.log('Main button not available:', e);
        }
        
        // Показываем информацию о пользователе
        this.displayUserInfo();
        
        // Добавляем кнопку переключения темы для тестирования в браузере (только если нет Telegram API)
        if (!window.Telegram?.WebApp?.themeParams || Object.keys(window.Telegram.WebApp.themeParams).length === 0) {
            this.addThemeToggleForTesting();
        }
    }
    
    // Инициализация наблюдателя за темой
    initializeThemeWatcher() {
        // Следим за изменениями цветовой схемы системы
        if (window.matchMedia) {
            const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
            darkModeQuery.addListener((e) => {
                console.log('System color scheme changed:', e.matches ? 'dark' : 'light');
                // Обновляем тему только если нет Telegram API
                if (!window.Telegram?.WebApp?.themeParams) {
                    this.setupTheme();
                }
            });
        }
        
        // Наблюдаем за изменениями в объекте Telegram
        let lastThemeParams = JSON.stringify(tg.themeParams);
        let lastColorScheme = tg.colorScheme;
        
        setInterval(() => {
            const currentThemeParams = JSON.stringify(tg.themeParams);
            const currentColorScheme = tg.colorScheme;
            
            if (currentThemeParams !== lastThemeParams || currentColorScheme !== lastColorScheme) {
                console.log('Telegram theme changed detected');
                this.setupTheme();
                lastThemeParams = currentThemeParams;
                lastColorScheme = currentColorScheme;
            }
        }, 1000);
    }
    
    // Утилита для тестирования тем в браузере
    addThemeToggleForTesting() {
        const testButton = document.createElement('button');
        testButton.innerHTML = '🎨 Тест темы';
        testButton.setAttribute('data-theme-test-button', 'true');
        testButton.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            z-index: 1000;
            padding: 8px 12px;
            background: var(--primary-color);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
            opacity: 0.8;
            transition: opacity 0.3s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        `;
        
        let isDarkTest = false;
        testButton.onclick = () => {
            isDarkTest = !isDarkTest;
            this.simulateTheme(isDarkTest);
            testButton.innerHTML = isDarkTest ? '☀️ Светлая' : '🌙 Темная';
        };
        
        testButton.onmouseenter = () => testButton.style.opacity = '1';
        testButton.onmouseleave = () => testButton.style.opacity = '0.8';
        
        document.body.appendChild(testButton);
        console.log('Theme toggle button added for testing');
    }
    
    // Симуляция Telegram темы для тестирования
    simulateTheme(isDark) {
        const mockThemeParams = isDark ? {
            bg_color: '#1c1c1e',
            text_color: '#ffffff',
            hint_color: '#8e8e93',
            secondary_bg_color: '#2c2c2e',
            button_color: '#0a84ff',
            button_text_color: '#ffffff'
        } : {
            bg_color: '#ffffff',
            text_color: '#000000',
            hint_color: '#8e8e93',
            secondary_bg_color: '#f2f2f7',
            button_color: '#2481cc',
            button_text_color: '#ffffff'
        };
        
        // Временно перезаписываем тему
        const originalColorScheme = tg.colorScheme;
        const originalThemeParams = tg.themeParams;
        
        tg.colorScheme = isDark ? 'dark' : 'light';
        tg.themeParams = mockThemeParams;
        
        this.setupTheme();
        
        console.log('Theme simulated:', { isDark, mockThemeParams });
    }
    
    setupTheme() {
        const root = document.documentElement;
        
        // Проверяем доступность themeParams
        const themeParams = tg.themeParams || {};
        let isDark = tg.colorScheme === 'dark';
        
        // Если Telegram API недоступен, используем системные предпочтения
        const hasTelegramTheme = window.Telegram?.WebApp?.themeParams && 
                                Object.keys(window.Telegram.WebApp.themeParams).length > 0;
        
        if (!hasTelegramTheme && window.matchMedia) {
            isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            console.log('Using system color scheme:', isDark ? 'dark' : 'light');
        }
        
        console.log('Setting up theme:', { 
            colorScheme: tg.colorScheme, 
            isDark, 
            hasTelegramTheme,
            themeParams 
        });
        
        // Устанавливаем цвета с надежными fallback значениями
        const colors = {
            bgColor: themeParams.bg_color || (isDark ? '#1c1c1e' : '#ffffff'),
            textColor: themeParams.text_color || (isDark ? '#ffffff' : '#000000'),
            hintColor: themeParams.hint_color || (isDark ? '#8e8e93' : '#8e8e93'),
            secondaryBgColor: themeParams.secondary_bg_color || (isDark ? '#2c2c2e' : '#f2f2f7'),
            linkColor: themeParams.link_color || (isDark ? '#0a84ff' : '#2481cc'),
            buttonColor: themeParams.button_color || (isDark ? '#0a84ff' : '#2481cc'),
            buttonTextColor: themeParams.button_text_color || '#ffffff'
        };
        
        // Применяем основные Telegram цвета
        root.style.setProperty('--tg-theme-bg-color', colors.bgColor);
        root.style.setProperty('--tg-theme-text-color', colors.textColor);
        root.style.setProperty('--tg-theme-hint-color', colors.hintColor);
        root.style.setProperty('--tg-theme-secondary-bg-color', colors.secondaryBgColor);
        root.style.setProperty('--tg-theme-link-color', colors.linkColor);
        root.style.setProperty('--tg-theme-button-color', colors.buttonColor);
        root.style.setProperty('--tg-theme-button-text-color', colors.buttonTextColor);
        
        // Устанавливаем дополнительные адаптивные переменные
        root.style.setProperty('--primary-color', colors.buttonColor);
        root.style.setProperty('--secondary-color', colors.secondaryBgColor);
        
        // Устанавливаем адаптивные цвета границ и теней в зависимости от темы
        const borderColor = isDark ? '#3a3a3c' : '#e9ecef';
        const shadowColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
        
        root.style.setProperty('--dynamic-border-color', borderColor);
        root.style.setProperty('--dynamic-shadow', `0 2px 10px ${shadowColor}`);
        
        // Применяем стили к body для немедленного эффекта
        document.body.style.backgroundColor = colors.bgColor;
        document.body.style.color = colors.textColor;
        
        // Добавляем класс темы для специальных случаев
        document.body.classList.toggle('dark-theme', isDark);
        document.body.classList.toggle('light-theme', !isDark);
        
        // Обновляем тестовую кнопку если она есть
        const testButton = document.querySelector('[data-theme-test-button]');
        if (testButton) {
            testButton.innerHTML = isDark ? '☀️ Светлая' : '🌙 Темная';
        }
        
        console.log('Theme applied successfully:', { 
            colors, 
            isDark, 
            borderColor, 
            shadowColor,
            themeSource: hasTelegramTheme ? 'Telegram' : 'System/Fallback'
        });
    }
    
    initializeUI() {
        console.log('Initializing UI elements...');
        
        // Скрываем все индикаторы загрузки при инициализации
        const loadingIndicators = [
            'libraryLoading', 
            'searchLoading', 
            'recommendationsLoading'
        ];
        
        loadingIndicators.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.classList.add('hidden');
            }
        });
        
        // Скрываем все контейнеры контента при инициализации
        const contentContainers = [
            'libraryPapersContainer',
            'searchResultsContainer', 
            'recommendationsContainer'
        ];
        
        contentContainers.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.classList.add('hidden');
            }
        });
        
        // Скрываем все пустые состояния при инициализации
        const emptyStates = [
            'libraryEmptyState'
        ];
        
        emptyStates.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.classList.add('hidden');
            }
        });
        
        // Скрываем пагинацию при инициализации
        const paginationElements = ['libraryPagination'];
        paginationElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.classList.add('hidden');
            }
        });
        
        // Скрываем статистику при инициализации
        const statsElements = ['statsPanel'];
        statsElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.classList.add('hidden');
            }
        });
        
        // Скрываем индикатор печати в чате
        this.showTypingIndicator(false);
        
        console.log('UI elements initialized and hidden');
    }
    
    // Инициализация адаптивной навигации
    initializeNavigation() {
        console.log('Initializing adaptive navigation...');
        const navigation = document.querySelector('.sa-navigation');
        
        if (!navigation) {
            console.log('Navigation not found');
            return;
        }
        
        // Функция обновления индикаторов прокрутки
        const updateScrollIndicators = () => {
            const scrollLeft = navigation.scrollLeft;
            const scrollWidth = navigation.scrollWidth;
            const clientWidth = navigation.clientWidth;
            const maxScrollLeft = scrollWidth - clientWidth;
            
            // Показываем левый индикатор если прокручено вправо
            navigation.classList.toggle('scrolled-right', scrollLeft > 5);
            
            // Скрываем правый индикатор если прокручено до конца
            navigation.classList.toggle('scrolled-end', scrollLeft >= maxScrollLeft - 5);
        };
        
        // Обработчик прокрутки навигации
        navigation.addEventListener('scroll', updateScrollIndicators);
        
        // Обработчик изменения размера окна
        window.addEventListener('resize', () => {
            setTimeout(updateScrollIndicators, 100);
        });
        
        // Первоначальное обновление
        setTimeout(updateScrollIndicators, 100);
        
        // Обеспечиваем видимость активной вкладки при переключении
        this.originalSwitchTab = this.switchTab.bind(this);
        this.switchTab = (tabName) => {
            this.originalSwitchTab(tabName);
            this.scrollToActiveTab();
        };
        
        console.log('Adaptive navigation initialized');
    }
    
    // Прокрутка к активной вкладке
    scrollToActiveTab() {
        const navigation = document.querySelector('.sa-navigation');
        const activeButton = navigation?.querySelector('.sa-nav-btn.active');
        
        if (!navigation || !activeButton) return;
        
        const navRect = navigation.getBoundingClientRect();
        const btnRect = activeButton.getBoundingClientRect();
        
        // Проверяем, видна ли активная кнопка
        if (btnRect.left < navRect.left || btnRect.right > navRect.right) {
            const scrollLeft = activeButton.offsetLeft - (navigation.clientWidth / 2) + (activeButton.offsetWidth / 2);
            navigation.scrollTo({
                left: Math.max(0, scrollLeft),
                behavior: 'smooth'
            });
        }
    }
    
    displayUserInfo() {
        const userInfo = document.getElementById('userInfo');
        if (!userInfo) return;
        
        const user = tg.initDataUnsafe?.user;
        
        if (user && user.first_name) {
            const name = user.first_name + (user.last_name ? ` ${user.last_name}` : '');
            userInfo.textContent = `👋 Привет, ${name}!`;
        } else {
            // Показываем общее приветствие для ПК или без авторизации Telegram
            userInfo.textContent = '👋 Добро пожаловать в научный ассистент!';
        }
    }
    
    bindEvents() {
        console.log('Binding events...');
        
        // Навигация между вкладками - множественный подход для надежности
        document.querySelectorAll('.sa-nav-btn').forEach(btn => {
            console.log('Binding to button:', btn.dataset.tab);
            
            // Стандартный обработчик
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const tab = e.currentTarget.dataset.tab;
                console.log('Button clicked (addEventListener):', tab);
                this.switchTab(tab);
            });
            
            // Дополнительный обработчик через onclick для надежности
            btn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                const tab = e.currentTarget.dataset.tab;
                console.log('Button clicked (onclick):', tab);
                this.switchTab(tab);
                return false;
            };
            
            // Touch события для мобильных устройств
            btn.addEventListener('touchstart', (e) => {
                e.preventDefault();
                const tab = e.currentTarget.dataset.tab;
                console.log('Button touched:', tab);
                this.switchTab(tab);
            }, { passive: false });
        });

        // События библиотеки
        this.bindLibraryEvents();
        
        // События поиска
        this.bindSearchEvents();
        
        // События рекомендаций
        this.bindRecommendationEvents();
        
        // События чата
        this.bindChatEvents();
        
        // События модального окна
        this.bindModalEvents();
    }
    
    bindLibraryEvents() {
        // Поиск по библиотеке
        const librarySearchInput = document.getElementById('librarySearchInput');
        const clearLibrarySearch = document.getElementById('clearLibrarySearch');
        
        librarySearchInput.addEventListener('input', (e) => {
            this.handleLibrarySearch(e.target.value);
            this.toggleClearButton(e.target.value, 'clearLibrarySearch');
        });
        
        clearLibrarySearch.addEventListener('click', () => {
            librarySearchInput.value = '';
            this.handleLibrarySearch('');
            this.toggleClearButton('', 'clearLibrarySearch');
        });
        
        // Фильтры библиотеки
        document.getElementById('tagFilter').addEventListener('change', (e) => {
            this.handleTagFilter(e.target.value);
        });
        
        document.getElementById('sortFilter').addEventListener('change', (e) => {
            this.handleSort(e.target.value);
        });
        
        // Пагинация библиотеки
        document.getElementById('libraryPrevPage').addEventListener('click', () => {
            this.changePage(this.currentPage - 1);
        });
        
        document.getElementById('libraryNextPage').addEventListener('click', () => {
            this.changePage(this.currentPage + 1);
        });
        
        // Переход к поиску из пустой библиотеки
        document.getElementById('goToSearch').addEventListener('click', () => {
            this.switchTab('search');
        });
    }
    
    bindSearchEvents() {
        // Выполнение поиска
        const searchInput = document.getElementById('searchInput');
        const executeSearchBtn = document.getElementById('executeSearch');
        
        const executeSearch = () => {
            const query = searchInput.value.trim();
            if (query) {
                this.performSearch();
            }
        };
        
        executeSearchBtn.addEventListener('click', executeSearch);
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                executeSearch();
            }
        });
    }
    
    bindRecommendationEvents() {
        document.getElementById('generateRecommendations').addEventListener('click', () => {
            this.generateRecommendations();
        });
    }
    
    bindChatEvents() {
        const chatInput = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendMessage');
        
        const sendMessage = () => {
            const message = chatInput.value.trim();
            if (message) {
                this.sendChatMessage(message);
                chatInput.value = '';
            }
        };
        
        sendBtn.addEventListener('click', sendMessage);
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }
    
    bindModalEvents() {
        document.getElementById('closeModal').addEventListener('click', () => {
            this.closeModal();
        });
        
        document.getElementById('paperModal').addEventListener('click', (e) => {
            if (e.target.id === 'paperModal') {
                this.closeModal();
            }
        });
        
        document.getElementById('openOriginal').addEventListener('click', () => {
            if (this.currentPaper?.url) {
                tg.openLink(this.currentPaper.url);
            }
        });
        
        document.getElementById('saveToLibrary').addEventListener('click', () => {
            if (this.currentPaper) {
                this.savePaperToLibrary(this.currentPaper);
            }
        });
        
        document.getElementById('deletePaper').addEventListener('click', () => {
            if (this.currentPaper) {
                this.deletePaper(this.currentPaper.external_id);
            }
        });
    }
    
    switchTab(tabName) {
        console.log('Switching to tab:', tabName);
        
        // Убираем активные классы с кнопок
        document.querySelectorAll('.sa-nav-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        
        // Скрываем все вкладки через CSS классы, а не принудительно
        document.querySelectorAll('.sa-tab-content').forEach(tab => {
            tab.classList.remove('active');
        });
        
        // Активируем нужную кнопку
        const activeButton = document.querySelector(`[data-tab="${tabName}"]`);
        if (activeButton) {
            activeButton.classList.add('active');
        }
        
        // Показываем нужную вкладку через CSS класс
        const activeTab = document.getElementById(`${tabName}-tab`);
        if (activeTab) {
            activeTab.classList.add('active');
        }
        
        this.currentTab = tabName;
        
        // Обновляем главную кнопку в зависимости от вкладки
        this.updateMainButton();
        
        // Haptic feedback (если доступно)
        this.haptic('impact', 'light');
        
        // Отладочная информация
        this.debugTabState();
        
        console.log('Tab switched successfully using CSS classes');
    }
    
    updateMainButton() {
        switch (this.currentTab) {
            case 'library':
                tg.MainButton.setText('Обновить библиотеку');
                break;
            case 'search':
                tg.MainButton.setText('Найти статьи');
                break;
            case 'recommendations':
                tg.MainButton.setText('Получить рекомендации');
                break;
            case 'chat':
                tg.MainButton.setText('Очистить чат');
                break;
        }
    }
    
    refreshCurrentTab() {
        switch (this.currentTab) {
            case 'library':
                this.loadLibrary();
                break;
            case 'search':
                this.performSearch();
                break;
            case 'recommendations':
                this.generateRecommendations();
                break;
            case 'chat':
                this.clearChat();
                break;
        }
    }
    
    
    toggleClearButton(value, buttonId = 'clearSearch') {
        const clearBtn = document.getElementById(buttonId);
        if (clearBtn) {
            clearBtn.classList.toggle('visible', value.length > 0);
        }
    }
    
    async loadLibrary(searchQuery = '') {
        try {
            this.showLoading(true, 'library');
            const url = new URL('/api/v1/library', window.location.origin);
            url.searchParams.append('page', '1');
            url.searchParams.append('per_page', '1000');
            if (searchQuery) {
                url.searchParams.append('search', searchQuery);
            }

            const response = await fetch(url, {
                headers: {
                    'X-Telegram-Init-Data': tg.initData
                }
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Не удалось загрузить библиотеку');
            }

            const data = await response.json();
            this.allPapers = data.papers;
            this.totalPapers = data.total_count;
            
            this.filteredPapers = [...this.allPapers];
            
            this.updateStats();
            this.updateTagFilter();
            this.displayPapers('library');
            this.updatePagination('library');
            console.log('Library loaded successfully'); 
            this.showLoading(false, 'library');
            this.toggleEmptyState(this.totalPapers === 0, 'library');

        } catch (error) {
            this.showError(`Ошибка загрузки библиотеки: ${error.message}`);
            this.toggleEmptyState(true, 'library');
        } finally {
            console.log('Library loading finished');
            this.showLoading(false, 'library');
        }
    }
    
    async performSearch() {
        const query = document.getElementById('searchInput').value.trim();
        if (!query) {
            tg.showAlert('Введите поисковый запрос');
            return;
        }
        
        this.showLoading(true, 'search');
        
        try {
            const searchRequest = {
                query: query,
                source: document.getElementById('sourceFilter').value,
                filters: {
                    author: document.getElementById('authorFilter').value,
                    year: document.getElementById('yearFilter').value ? parseInt(document.getElementById('yearFilter').value) : null
                },
                limit: parseInt(document.getElementById('limitFilter').value) || 10
            };
            
            // Удаляем пустые фильтры
            Object.keys(searchRequest.filters).forEach(key => {
                if (!searchRequest.filters[key]) {
                    delete searchRequest.filters[key];
                }
            });
            
            const response = await fetch('/api/v1/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg.initData
                },
                body: JSON.stringify(searchRequest)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Ошибка поиска');
            }
            
            const data = await response.json();
            this.displaySearchResults(data.papers);
            
        } catch (error) {
            this.showError(`Ошибка поиска: ${error.message}`);
        } finally {
            this.showLoading(false, 'search');
        }
    }
    
    async generateRecommendations() {
        this.showLoading(true, 'recommendations');
        
        try {
            const response = await fetch('/api/v1/recommendations', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg.initData
                },
                body: JSON.stringify({
                    paper_ids: [], // Рекомендации на основе всей библиотеки
                    limit: 15
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Ошибка получения рекомендаций');
            }
            
            const data = await response.json();
            
            if (data.papers.length === 0) {
                document.getElementById('recommendationsContainer').innerHTML = 
                    '<div class="empty-state"><p>Рекомендации не найдены. Добавьте статьи в библиотеку для получения персональных рекомендаций.</p></div>';
            } else {
                this.displaySearchResults(data.papers, 'recommendations');
            }
            
        } catch (error) {
            this.showError(`Ошибка получения рекомендаций: ${error.message}`);
        } finally {
            this.showLoading(false, 'recommendations');
        }
    }
    
    async sendChatMessage(message) {
        // Добавляем сообщение пользователя
        this.addChatMessage(message, 'user');
        
        // Показываем индикатор печати
        this.showTypingIndicator(true);
        
        try {
            const response = await fetch('/api/v1/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg.initData
                },
                body: JSON.stringify({
                    message: message,
                    context: this.chatHistory.slice(-10) // Последние 10 сообщений
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Ошибка обработки сообщения');
            }
            
            const data = await response.json();
            
            // Добавляем ответ бота
            this.addChatMessage(data.response_text, 'bot');
            
            // Выполняем действие если необходимо
            if (data.action) {
                this.handleChatAction(data);
            }
            
        } catch (error) {
            this.addChatMessage(`Извините, произошла ошибка: ${error.message}`, 'bot');
        } finally {
            this.showTypingIndicator(false);
        }
    }
    
    addChatMessage(message, sender) {
        const messagesContainer = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = message;
        
        messageDiv.appendChild(messageContent);
        messagesContainer.appendChild(messageDiv);
        
        // Прокручиваем вниз
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        // Сохраняем в истории
        this.chatHistory.push({ message, sender, timestamp: new Date() });
        
        // Haptic feedback для новых сообщений
        if (sender === 'bot') {
            this.haptic('notification', 'success');
        }
    }
    
    showTypingIndicator(show) {
        const indicator = document.getElementById('typingIndicator');
        indicator.classList.toggle('hidden', !show);
        
        if (show) {
            const messagesContainer = document.getElementById('chatMessages');
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
    
    handleChatAction(data) {
        switch (data.action) {
            case 'search':
                // Переключаемся на вкладку поиска и выполняем поиск
                this.switchTab('search');
                document.getElementById('searchInput').value = data.data.query;
                if (data.data.filters.author) {
                    document.getElementById('authorFilter').value = data.data.filters.author;
                }
                if (data.data.filters.year) {
                    document.getElementById('yearFilter').value = data.data.filters.year;
                }
                setTimeout(() => this.performSearch(), 500);
                break;
                
            case 'show_library':
                this.switchTab('library');
                break;
                
            case 'summarize':
                tg.showAlert('Функция резюмирования статей будет доступна в следующем обновлении');
                break;
        }
    }
    
    clearChat() {
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.innerHTML = `
            <div class="message bot-message">
                <div class="message-content">
                    Привет! Я ваш научный ассистент. Напишите, что вас интересует, и я помогу найти статьи или ответить на вопросы.
                </div>
            </div>
        `;
        this.chatHistory = [];
        
        // Скрываем индикатор печати
        this.showTypingIndicator(false);
        
        this.haptic('impact', 'medium');
    }
    
    showLoading(show, context = 'library') {
        const loadingId = `${context}Loading`;
        const containerId = context === 'library' ? 'libraryPapersContainer' :
                            context === 'search' ? 'searchResultsContainer' :
                            'recommendationsContainer';
        const paginationId = context === 'library' ? 'libraryPagination' : null;
        const statsId = context === 'library' ? 'statsPanel' : null;

        const loadingEl = document.getElementById(loadingId);
        const containerEl = document.getElementById(containerId);
        const paginationEl = document.getElementById(paginationId);
        const statsEl = document.getElementById(statsId);
        console.log(`Toggling loading state: ${show} for context: ${context}`);
        console.log('Elements:', {
            loading: loadingEl,
            container: containerEl,
            pagination: paginationEl,
            stats: statsEl
        });
        if (loadingEl) loadingEl.classList.toggle('hidden', !show);
        if (containerEl) containerEl.classList.toggle('hidden', show);
        if (paginationEl) paginationEl.classList.toggle('hidden', show);
        if (statsEl) statsEl.classList.toggle('hidden', show);
    }

    toggleEmptyState(isEmpty, context = 'library') {
        const emptyStateId = `${context}EmptyState`;
        const containerId = context === 'library' ? 'libraryPapersContainer' :
                           context === 'search' ? 'searchResultsContainer' :
                           'recommendationsContainer';
        const paginationId = context === 'library' ? 'libraryPagination' : null;
        const statsId = context === 'library' ? 'statsPanel' : null;

        const emptyEl = document.getElementById(emptyStateId);
        const containerEl = document.getElementById(containerId);
        const paginationEl = document.getElementById(paginationId);
        const statsEl = document.getElementById(statsId);

        if (emptyEl) emptyEl.classList.toggle('hidden', !isEmpty);
        if (containerEl) containerEl.classList.toggle('hidden', isEmpty);
        if (paginationEl) paginationEl.classList.toggle('hidden', isEmpty);
        if (statsId) statsEl.classList.toggle('hidden', isEmpty);
    }
    
    updateStats() {
        document.getElementById('totalPapers').textContent = this.totalPapers;
    }
    
    updateTagFilter() {
        const tagFilter = document.getElementById('tagFilter');
        const tags = new Set();
        
        this.allPapers.forEach(paper => {
            if (paper.tags) {
                paper.tags.forEach(tag => tags.add(tag));
            }
        });
        
        // Очищаем и добавляем опции
        tagFilter.innerHTML = '<option value="">Все теги</option>';

        [...tags].sort().forEach(tag => {
            const option = document.createElement('option');
            option.value = tag;
            option.textContent = tag;
            tagFilter.appendChild(option);
        });
    }
    
    handleLibrarySearch(query) {
        const searchTerm = query.toLowerCase().trim();
        
        if (!searchTerm) {
            this.filteredPapers = [...this.allPapers];
        } else {
            this.filteredPapers = this.allPapers.filter(paper => 
                paper.title.toLowerCase().includes(searchTerm) ||
                paper.authors.join ? paper.authors.join(', ').toLowerCase().includes(searchTerm) :
                paper.authors.toLowerCase().includes(searchTerm) ||
                paper.abstract.toLowerCase().includes(searchTerm)
            );
        }
        
        this.currentPage = 1;
        this.displayPapers('library');
        this.updatePagination('library');
    }
    
    handleTagFilter(tag) {
        if (!tag) {
            this.filteredPapers = [...this.allPapers];
        } else {
            this.filteredPapers = this.allPapers.filter(paper => 
                paper.tags && paper.tags.includes(tag)
            );
        }
        
        this.currentPage = 1;
        this.displayPapers('library');
        this.updatePagination('library');
    }
    
    handleSort(sortType) {
        this.filteredPapers.sort((a, b) => {
            switch (sortType) {
                case 'saved_at_desc':
                    return new Date(b.saved_at) - new Date(a.saved_at);
                case 'saved_at_asc':
                    return new Date(a.saved_at) - new Date(b.saved_at);
                case 'title_asc':
                    return a.title.localeCompare(b.title);
                case 'title_desc':
                    return b.title.localeCompare(a.title);
                default:
                    return 0;
            }
        });
        
        this.displayPapers('library');
    }
    
    displayPapers(context = 'library') {
        const containerId = context === 'library' ? 'libraryPapersContainer' : 
                           context === 'search' ? 'searchResultsContainer' :
                           'recommendationsContainer';
        
        const container = document.getElementById(containerId);
        
        let papersToShow;
        if (context === 'library') {
            const startIndex = (this.currentPage - 1) * this.perPage;
            const endIndex = startIndex + this.perPage;
            papersToShow = this.filteredPapers.slice(startIndex, endIndex);
        } else {
            papersToShow = this.filteredPapers; // Для поиска и рекомендаций показываем все
        }
        
        container.innerHTML = '';
        
        papersToShow.forEach(paper => {
            const paperElement = this.createPaperCard(paper, context);
            container.appendChild(paperElement);
        });
        
        // Добавляем haptic feedback
        this.haptic('impact', 'light');
    }
    
    displaySearchResults(papers, context = 'search') {
        this.filteredPapers = papers;
        this.displayPapers(context);
    }
    
    createPaperCard(paper, context = 'library') {
        const card = document.createElement('div');
        card.className = 'paper-card';
        card.onclick = () => this.openPaperModal(paper, context);
        
        const tagsHtml = paper.tags 
            ? paper.tags.map(tag => `<span class="category-tag">${tag}</span>`).join('')
            : '';
        
        const publishedDate = paper.publication_date 
            ? new Date(paper.publication_date).toLocaleDateString('ru-RU')
            : 'Дата не указана';
        
        const savedDate = paper.saved_at 
            ? new Date(paper.saved_at).toLocaleDateString('ru-RU')
            : '';
            
        // Обрабатываем авторов
        const authors = Array.isArray(paper.authors) 
            ? paper.authors.join(', ')
            : paper.authors || 'Неизвестные авторы';
            
        const externalIds = this.allPapers.map(p => p.external_id);

        card.innerHTML = `
            <h3 class="paper-title">${this.escapeHtml(paper.title)}</h3>
            <div class="paper-authors">${this.escapeHtml(authors)}</div>
            <div class="paper-meta">
                <span class="paper-date">📅 ${publishedDate}</span>
                <div class="paper-tags">${tagsHtml}</div>
            </div>
            <p class="paper-abstract">${this.escapeHtml(this.truncateText(paper.abstract, 200))}</p>
            <div class="paper-actions" onclick="event.stopPropagation();">
                <button class="action-btn view-btn">
                    👁 Подробнее
                </button>
                ${context === 'library' || externalIds.includes(paper.external_id) ? 
                    '<button class="action-btn delete-btn">🗑 Удалить</button>' : 
                    '<button class="action-btn save-btn">💾 Сохранить</button>'
                }
            </div>
        `;
        
        // Add event listeners programmatically
        const viewBtn = card.querySelector('.view-btn');
        const actionBtn = card.querySelector('.delete-btn, .save-btn');
        
        viewBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openPaperModal(paper, context);
        });
        
        if (actionBtn) {
            actionBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (context === 'library') {
                    this.deletePaper(paper.external_id);
                } else {
                    if (paper in this.allPapers) {
                        this.showAlert('Статья уже сохранена в библиотеку');
                    } else {
                        this.savePaperToLibrary(paper);
                    }
                }
            });
        }
        
        return card;
    }
    
    openPaperModal(paper, context = 'library') {
        this.currentPaper = paper;
        const modal = document.getElementById('paperModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalBody = document.getElementById('modalBody');
        
        modalTitle.textContent = paper.title;

        const publishedDate = paper.publication_date
            ? new Date(paper.publication_date).toLocaleDateString('ru-RU')
            : 'Дата не указана';
            
        const tagsHtml = paper.tags 
            ? paper.tags.map(tag => `<span class="category-tag">${tag}</span>`).join('')
            : 'Без категории';
        
        const authors = Array.isArray(paper.authors) 
            ? paper.authors.join(', ')
            : paper.authors || 'Неизвестные авторы';

        const externalIds = this.allPapers.map(p => p.external_id);

        modalBody.innerHTML = `
            <div style="margin-bottom: 16px;">
                <strong>Авторы:</strong><br>
                ${this.escapeHtml(authors)}
            </div>
            
            <div style="margin-bottom: 16px;">
                <strong>Дата публикации:</strong> ${publishedDate}
            </div>
            
            <div style="margin-bottom: 16px;">
                <strong>Категории:</strong>
                ${context === 'library' ? '<button id="editTagsBtn" class="action-btn" style="margin-left: 8px; padding: 2px 6px; font-size: 12px;">✏️</button>' : ''}
                <br>
                <div style="margin-top: 8px;">${tagsHtml}</div>
            </div>
            
            <div style="margin-bottom: 16px;">
                <strong>Аннотация:</strong><br>
                <p style="margin-top: 8px; line-height: 1.6;">${paper.abstract}</p>
            </div>
            
            ${paper.external_id ? `<div style="margin-bottom: 16px;">
                <strong>${paper.source || 'ID'}:</strong> ${paper.external_id}
            </div>` : ''}
        `;
        
        // Настраиваем кнопки в футере
        const saveBtn = document.getElementById('saveToLibrary');
        const deleteBtn = document.getElementById('deletePaper');
        
        if (context === 'library' || externalIds.includes(paper.external_id)) {
            saveBtn.classList.add('hidden');
            deleteBtn.classList.remove('hidden');
        } else {
            saveBtn.classList.remove('hidden');
            deleteBtn.classList.add('hidden');
        }
        
        modal.classList.add('visible');
        
        // Добавляем обработчик для редактирования тегов (только для библиотеки)
        if (context === 'library') {
            const editBtn = document.getElementById('editTagsBtn');
            if (editBtn) {
                editBtn.replaceWith(editBtn.cloneNode(true));
                document.getElementById('editTagsBtn').addEventListener('click', () => this.editTags());
            }
        }
        
        // Haptic feedback
        this.haptic('impact', 'medium');
    }
    
    closeModal() {
        const modal = document.getElementById('paperModal');
        modal.classList.remove('visible');
        this.currentPaper = null;
    }
    
    async deletePaper(paperId) {
        console.log('deletePaper called with ID:', paperId);
        const showConfirm = (message => {
            return new Promise((resolve) => {
                tg.showPopup({
                title: "Подтвердить",
                message,
                buttons: [
                    {id: 'ok', type: 'default', text: 'ОК'},
                    {id: 'cancel', type: 'cancel', text: 'Отмена'}
                ]
                }, (buttonId) => {
                resolve(buttonId === 'ok');
                });
            });
            })
        const result = await showConfirm('Вы уверены, что хотите удалить эту статью из библиотеки?')
        console.log(result)
        if (!result) {
            console.log('User cancelled deletion');
            return;
        }
        
        try {
            console.log('Sending delete request for paper:', paperId);
            const initData = tg.initData;
            const response = await fetch(`/api/v1/library/${paperId}`, {
                method: 'DELETE',
                headers: {
                    'X-Telegram-Init-Data': initData,
                    'Content-Type': 'application/json'
                }
            });
            
            console.log('Delete response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            // Удаляем из локального массива
            this.allPapers = this.allPapers.filter(paper => paper.external_id !== paperId);
            this.filteredPapers = this.filteredPapers.filter(paper => paper.external_id !== paperId);
            this.totalPapers--;
            
            // Обновляем интерфейс
            this.updateStats();
            this.displayPapers();
            this.updatePagination();
            this.closeModal();
            
            // Показываем пустое состояние если нужно
            this.toggleEmptyState(this.allPapers.length === 0);
            
            tg.showAlert('Статья удалена из библиотеки');
            this.haptic('notification', 'success');
            
        } catch (error) {
            console.error('Ошибка удаления статьи:', error);
            tg.showAlert('Не удалось удалить статью');
            this.haptic('notification', 'error');
        }
    }
    

    showInputDialogAsync(title, placeholder, defaultValue = '') {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            `;

            const dialog = document.createElement('div');
            dialog.style.cssText = `
                background: var(--tg-theme-bg-color, #fff);
                color: var(--tg-theme-text-color, #000);
                padding: 20px;
                border-radius: 12px;
                width: 90%;
                max-width: 400px;
                box-shadow: 0 4px 16px rgba(0,0,0,0.3);
            `;

            // Экранируем HTML для безопасности
            const escapeHtml = (text) => text.replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            })[m]);

            dialog.innerHTML = `
                <h3 style="margin: 0 0 15px 0; font-size: 18px;">${escapeHtml(title)}</h3>
                <input type="text" id="inputField"
                    placeholder="${escapeHtml(placeholder)}"
                    style="width: 100%; padding: 12px; border: 1px solid var(--tg-theme-hint-color, #ccc); 
                            border-radius: 8px; font-size: 16px; background: var(--tg-theme-bg-color, #fff); 
                            color: var(--tg-theme-text-color, #000); box-sizing: border-box;">
                <div style="margin-top: 20px; text-align: right;">
                    <button id="cancelBtn" style="margin-right: 10px; padding: 10px 20px; 
                            background: transparent; color: var(--tg-theme-link-color, #0088cc); 
                            border: none; border-radius: 6px; cursor: pointer;">Отмена</button>
                    <button id="saveBtn" style="padding: 10px 20px; 
                            background: var(--tg-theme-button-color, #0088cc); 
                            color: var(--tg-theme-button-text-color, #fff); 
                            border: none; border-radius: 6px; cursor: pointer;">Сохранить</button>
                </div>
            `;

            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            const input = dialog.querySelector('#inputField');
            
            // ВАЖНО: устанавливаем значение после добавления в DOM
            input.value = defaultValue;
            input.focus();
            
            // Выделяем весь текст для удобства редактирования
            if (defaultValue) {
                input.select();
            }

            // Остальной код обработчиков...
            const closeDialog = () => {
                if (document.body.contains(overlay)) {
                    document.body.removeChild(overlay);
                }
            };

            dialog.querySelector('#saveBtn').onclick = () => {
                resolve(input.value);
                closeDialog();
            };

            dialog.querySelector('#cancelBtn').onclick = () => {
                resolve(null);
                closeDialog();
            };

            input.onkeydown = (e) => {
                if (e.key === 'Enter') {
                    resolve(input.value);
                    closeDialog();
                }
                if (e.key === 'Escape') {
                    resolve(null);
                    closeDialog();
                }
            };

            overlay.onclick = (e) => {
                if (e.target === overlay) {
                    resolve(null);
                    closeDialog();
                }
            };
        });
    }




    async editTags() {
        console.log('editTags called');
        if (!this.currentPaper) {
            console.log('No current paper selected');
            return;
        }

        const currentTags = this.currentPaper.tags ? this.currentPaper.tags.join(', ') : '';
        console.log('Current tags:', currentTags);
        
        // Use standard prompt instead of tg.showPrompt
        const newTagsStr = await this.showInputDialogAsync(
            'Редактирование тегов',
            currentTags ? 'Измените теги или добавьте новые' : 'Введите теги через запятую',
            currentTags
        );
        console.log('User input:', newTagsStr);
        
        if (newTagsStr === null) return;

        // Сравниваем с текущими для оптимизации
        if (newTagsStr.trim() === currentTags.trim()) {
            console.log('Теги не изменились');
            return;
        }

        try {
            const encodedExternalId = this.currentPaper.external_id.replace('/', 'BACKSLASH');
            console.log('Sending request to update tags for paper:', encodedExternalId);

            const response = await fetch(`/api/v1/library/${encodedExternalId}/tags`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg.initData
                },
                body: JSON.stringify({ new_tags: newTagsStr })
            });

            console.log('Response status:', response.status);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Не удалось обновить теги');
            }

            tg.showAlert('Теги успешно обновлены!');
            
            // Update UI
            this.currentPaper.tags = newTagsStr.split(',').map(t => t.trim()).filter(t => t);
            this.openPaperModal(this.currentPaper); // Re-open modal to show changes
            
            // Also update the main list
            const paperInList = this.allPapers.find(p => p.id === this.currentPaper.id);
            if (paperInList) {
                paperInList.tags = this.currentPaper.tags;
            }
            const paperInFilteredList = this.filteredPapers.find(p => p.id === this.currentPaper.id);
            if (paperInFilteredList) {
                paperInFilteredList.tags = this.currentPaper.tags;
            }

            this.displayPapers(); // Redraw paper list
            this.updateTagFilter(); // Update tag filter with new tags

        } catch (error) {
            console.error('Error updating tags:', error);
            this.showError(`Ошибка при обновлении тегов: ${error.message}`);
        }
    }
    
    async savePaperToLibrary(paper) {
        try {
            const response = await fetch('/api/v1/library/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg.initData
                },
                body: JSON.stringify({ paper })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Не удалось сохранить статью');
            }

            tg.showAlert('Статья успешно сохранена в библиотеку!');
        } catch (error) {
            this.showError(`Ошибка сохранения статьи: ${error.message}`);
        }
    }
    
    changePage(newPage) {
        const totalPages = Math.ceil(this.filteredPapers.length / this.perPage);
        
        if (newPage < 1 || newPage > totalPages) return;
        
        this.currentPage = newPage;
        this.displayPapers('library');
        this.updatePagination('library');
        
        // Прокручиваем наверх
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    updatePagination(context = 'library') {
        if (context !== 'library') return; // Пагинация только для библиотеки
        
        const totalPages = Math.ceil(this.filteredPapers.length / this.perPage);
        const prevBtn = document.getElementById('libraryPrevPage');
        const nextBtn = document.getElementById('libraryNextPage');
        const pageInfo = document.getElementById('libraryPageInfo');
        
        if (prevBtn) prevBtn.disabled = this.currentPage <= 1;
        if (nextBtn) nextBtn.disabled = this.currentPage >= totalPages;
        
        if (pageInfo) {
            pageInfo.textContent = totalPages > 0 
                ? `Страница ${this.currentPage} из ${totalPages}`
                : 'Нет страниц';
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    truncateText(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }
    
    showError(message) {
        console.error(message);
        tg.showAlert(message);
    }
}

// Инициализация приложения
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing app...');
    
    // Мягкая инициализация вкладок с поддержкой темизации
    const initializeTabs = () => {
        console.log('Initializing tabs with theme support...');
        
        // Используем CSS классы вместо принудительного style
        document.querySelectorAll('.sa-tab-content').forEach((tab, index) => {
            tab.classList.remove('active');
            // Не устанавливаем style.display напрямую, позволяем CSS управлять
        });
        
        // Показываем первую вкладку (библиотека) через CSS класс
        const libraryTab = document.getElementById('library-tab');
        if (libraryTab) {
            libraryTab.classList.add('active');
        }
        
        // Активируем первую кнопку навигации
        document.querySelectorAll('.sa-nav-btn').forEach(btn => btn.classList.remove('active'));
        const firstBtn = document.querySelector('.sa-nav-btn[data-tab="library"]');
        if (firstBtn) {
            firstBtn.classList.add('active');
        }
        
        console.log('Tabs initialized with CSS classes');
    };
    
    // Дополнительная инициализация темы в DOM
    const enhanceThemeInDOM = () => {
        console.log('Enhancing theme in DOM...');
        const root = document.documentElement;
        const tgObj = window.Telegram?.WebApp;
        
        if (tgObj && tgObj.themeParams) {
            const themeParams = tgObj.themeParams;
            const isDark = tgObj.colorScheme === 'dark';
            
            // Применяем дополнительные цвета, которые могли не примениться ранее
            if (themeParams.hint_color) {
                root.style.setProperty('--tg-theme-hint-color', themeParams.hint_color);
            }
            if (themeParams.link_color) {
                root.style.setProperty('--tg-theme-link-color', themeParams.link_color);
            }
            if (themeParams.button_text_color) {
                root.style.setProperty('--tg-theme-button-text-color', themeParams.button_text_color);
            }
            
            // Применяем адаптивные цвета
            const borderColor = isDark ? '#3a3a3c' : '#e9ecef';
            const shadowColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
            
            root.style.setProperty('--dynamic-border-color', borderColor);
            root.style.setProperty('--dynamic-shadow', `0 2px 10px ${shadowColor}`);
            
            console.log('Enhanced theme applied in DOM:', { isDark, borderColor, shadowColor });
        } else {
            console.log('Using fallback theme - no Telegram theme available');
        }
    };
    
    // Применяем улучшенную тему
    enhanceThemeInDOM();
    
    // Инициализируем вкладки мягко
    initializeTabs();
    
    // Создаем приложение
    window.app = new ScientificAssistantApp();
});

// Обработка ошибок
window.addEventListener('error', (event) => {
    console.error('Глобальная ошибка:', event.error);
    tg.showAlert('Произошла ошибка в приложении');
});
