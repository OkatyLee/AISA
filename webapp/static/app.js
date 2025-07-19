// Telegram Mini App API
const tg = window.Telegram.WebApp;

class LibraryApp {
    constructor() {
        this.currentPage = 1;
        this.perPage = 10;
        this.totalPapers = 0;
        this.allPapers = [];
        this.filteredPapers = [];
        this.currentPaper = null;
        
        this.initializeApp();
        this.bindEvents();
        this.loadLibrary();
    }
    
    initializeApp() {
        // Расширяем Mini App на весь экран
        tg.expand();
        
        // Настраиваем цвета темы
        this.setupTheme();
        
        // Настраиваем главную кнопку
        tg.MainButton.setText('Обновить');
        tg.MainButton.onClick(() => this.loadLibrary());
        tg.MainButton.show();
        
        // Показываем информацию о пользователе
        this.displayUserInfo();
    }
    
    setupTheme() {
        const root = document.documentElement;
        
        if (tg.colorScheme === 'dark') {
            root.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#1c1c1e');
            root.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#ffffff');
            root.style.setProperty('--tg-theme-hint-color', tg.themeParams.hint_color || '#8e8e93');
            root.style.setProperty('--tg-theme-secondary-bg-color', tg.themeParams.secondary_bg_color || '#2c2c2e');
        } else {
            root.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#ffffff');
            root.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#000000');
            root.style.setProperty('--tg-theme-hint-color', tg.themeParams.hint_color || '#8e8e93');
            root.style.setProperty('--tg-theme-secondary-bg-color', tg.themeParams.secondary_bg_color || '#f2f2f7');
        }
    }
    
    displayUserInfo() {
        const userInfo = document.getElementById('userInfo');
        const user = tg.initDataUnsafe?.user;
        
        if (user) {
            const name = user.first_name + (user.last_name ? ` ${user.last_name}` : '');
            userInfo.textContent = `👋 Привет, ${name}!`;
        }
    }
    
    bindEvents() {
        // Поиск
        const searchInput = document.getElementById('searchInput');
        const clearSearch = document.getElementById('clearSearch');
        
        searchInput.addEventListener('input', (e) => {
            this.handleSearch(e.target.value);
            this.toggleClearButton(e.target.value);
        });
        
        clearSearch.addEventListener('click', () => {
            searchInput.value = '';
            this.handleSearch('');
            this.toggleClearButton('');
        });
        
        // Фильтры
        document.getElementById('categoryFilter').addEventListener('change', (e) => {
            this.handleCategoryFilter(e.target.value);
        });
        
        document.getElementById('sortFilter').addEventListener('change', (e) => {
            this.handleSort(e.target.value);
        });
        
        // Пагинация
        document.getElementById('prevPage').addEventListener('click', () => {
            this.changePage(this.currentPage - 1);
        });
        
        document.getElementById('nextPage').addEventListener('click', () => {
            this.changePage(this.currentPage + 1);
        });
        
        // Модальное окно
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
        
        document.getElementById('deletePaper').addEventListener('click', () => {
            this.deletePaper(this.currentPaper.id);
        });
        
        // Кнопка "Открыть бота"
        document.getElementById('openBot').addEventListener('click', () => {
            tg.close();
        });
    }
    
    toggleClearButton(value) {
        const clearBtn = document.getElementById('clearSearch');
        clearBtn.classList.toggle('visible', value.length > 0);
    }
    
    async loadLibrary() {
        try {
            this.showLoading(true);
            
            const initData = tg.initData;
            const response = await fetch('/api/v1/library', {
                headers: {
                    'X-Telegram-Init-Data': initData,
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.allPapers = data.papers;
            this.filteredPapers = [...this.allPapers];
            this.totalPapers = data.total_count;
            
            this.updateStats();
            this.updateCategoryFilter();
            this.displayPapers();
            this.updatePagination();
            
            // Скрываем/показываем соответствующие элементы
            this.toggleEmptyState(this.allPapers.length === 0);
            
        } catch (error) {
            console.error('Ошибка загрузки библиотеки:', error);
            this.showError('Не удалось загрузить библиотеку. Попробуйте позже.');
            tg.showAlert('Ошибка загрузки данных');
        } finally {
            this.showLoading(false);
        }
    }
    
    showLoading(show) {
        document.getElementById('loading').classList.toggle('hidden', !show);
        document.getElementById('papersContainer').classList.toggle('hidden', show);
        document.getElementById('pagination').classList.toggle('hidden', show);
    }
    
    toggleEmptyState(isEmpty) {
        document.getElementById('emptyState').classList.toggle('hidden', !isEmpty);
        document.getElementById('papersContainer').classList.toggle('hidden', isEmpty);
        document.getElementById('pagination').classList.toggle('hidden', isEmpty);
        document.getElementById('statsPanel').classList.toggle('hidden', isEmpty);
    }
    
    updateStats() {
        document.getElementById('totalPapers').textContent = this.totalPapers;
    }
    
    updateCategoryFilter() {
        const categoryFilter = document.getElementById('categoryFilter');
        const categories = new Set();
        
        this.allPapers.forEach(paper => {
            if (paper.categories) {
                paper.categories.forEach(cat => categories.add(cat));
            }
        });
        
        // Очищаем и добавляем опции
        categoryFilter.innerHTML = '<option value="">Все категории</option>';
        
        [...categories].sort().forEach(category => {
            const option = document.createElement('option');
            option.value = category;
            option.textContent = category;
            categoryFilter.appendChild(option);
        });
    }
    
    handleSearch(query) {
        const searchTerm = query.toLowerCase().trim();
        
        if (!searchTerm) {
            this.filteredPapers = [...this.allPapers];
        } else {
            this.filteredPapers = this.allPapers.filter(paper => 
                paper.title.toLowerCase().includes(searchTerm) ||
                paper.authors.toLowerCase().includes(searchTerm) ||
                paper.abstract.toLowerCase().includes(searchTerm)
            );
        }
        
        this.currentPage = 1;
        this.displayPapers();
        this.updatePagination();
    }
    
    handleCategoryFilter(category) {
        if (!category) {
            this.filteredPapers = [...this.allPapers];
        } else {
            this.filteredPapers = this.allPapers.filter(paper => 
                paper.categories && paper.categories.includes(category)
            );
        }
        
        this.currentPage = 1;
        this.displayPapers();
        this.updatePagination();
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
        
        this.displayPapers();
    }
    
    displayPapers() {
        const container = document.getElementById('papersContainer');
        const startIndex = (this.currentPage - 1) * this.perPage;
        const endIndex = startIndex + this.perPage;
        const papersToShow = this.filteredPapers.slice(startIndex, endIndex);
        
        container.innerHTML = '';
        
        papersToShow.forEach(paper => {
            const paperElement = this.createPaperCard(paper);
            container.appendChild(paperElement);
        });
        
        // Добавляем haptic feedback
        tg.HapticFeedback.impactOccurred('light');
    }
    
    createPaperCard(paper) {
        const card = document.createElement('div');
        card.className = 'paper-card';
        card.onclick = () => this.openPaperModal(paper);
        
        const categoriesHtml = paper.categories 
            ? paper.categories.map(cat => `<span class="category-tag">${cat}</span>`).join('')
            : '';
        
        const publishedDate = paper.published_date 
            ? new Date(paper.published_date).toLocaleDateString('ru-RU')
            : 'Дата не указана';
        
        const savedDate = paper.saved_at 
            ? new Date(paper.saved_at).toLocaleDateString('ru-RU')
            : '';
            
        card.innerHTML = `
            <h3 class="paper-title">${this.escapeHtml(paper.title)}</h3>
            <div class="paper-authors">${this.escapeHtml(paper.authors)}</div>
            <div class="paper-meta">
                <span class="paper-date">📅 ${publishedDate}</span>
                <div class="paper-categories">${categoriesHtml}</div>
            </div>
            <p class="paper-abstract">${this.escapeHtml(this.truncateText(paper.abstract, 200))}</p>
            <div class="paper-actions" onclick="event.stopPropagation();">
                <button class="action-btn view-btn" onclick="event.stopPropagation(); app.openPaperModal(${JSON.stringify(paper).replace(/"/g, '&quot;')});">
                    👁 Подробнее
                </button>
                <button class="action-btn delete-btn" onclick="event.stopPropagation(); app.deletePaper(${paper.id});">
                    🗑 Удалить
                </button>
            </div>
        `;
        
        return card;
    }
    
    openPaperModal(paper) {
        this.currentPaper = paper;
        const modal = document.getElementById('paperModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalBody = document.getElementById('modalBody');
        
        modalTitle.textContent = paper.title;
        
        const publishedDate = paper.published_date 
            ? new Date(paper.published_date).toLocaleDateString('ru-RU')
            : 'Дата не указана';
            
        const categoriesHtml = paper.categories 
            ? paper.categories.map(cat => `<span class="category-tag">${cat}</span>`).join('')
            : 'Без категории';
        
        modalBody.innerHTML = `
            <div style="margin-bottom: 16px;">
                <strong>Авторы:</strong><br>
                ${this.escapeHtml(paper.authors)}
            </div>
            
            <div style="margin-bottom: 16px;">
                <strong>Дата публикации:</strong> ${publishedDate}
            </div>
            
            <div style="margin-bottom: 16px;">
                <strong>Категории:</strong><br>
                <div style="margin-top: 8px;">${categoriesHtml}</div>
            </div>
            
            <div style="margin-bottom: 16px;">
                <strong>Аннотация:</strong><br>
                <p style="margin-top: 8px; line-height: 1.6;">${this.escapeHtml(paper.abstract)}</p>
            </div>
            
            ${paper.arxiv_id ? `<div style="margin-bottom: 16px;">
                <strong>ArXiv ID:</strong> ${paper.arxiv_id}
            </div>` : ''}
        `;
        
        modal.classList.add('visible');
        
        // Haptic feedback
        tg.HapticFeedback.impactOccurred('medium');
    }
    
    closeModal() {
        const modal = document.getElementById('paperModal');
        modal.classList.remove('visible');
        this.currentPaper = null;
    }
    
    async deletePaper(paperId) {
        const result = await tg.showConfirm('Вы уверены, что хотите удалить эту статью из библиотеки?');
        
        if (!result) return;
        
        try {
            const initData = tg.initData;
            const response = await fetch(`/api/v1/library/${paperId}`, {
                method: 'DELETE',
                headers: {
                    'X-Telegram-Init-Data': initData,
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            // Удаляем из локального массива
            this.allPapers = this.allPapers.filter(paper => paper.id !== paperId);
            this.filteredPapers = this.filteredPapers.filter(paper => paper.id !== paperId);
            this.totalPapers--;
            
            // Обновляем интерфейс
            this.updateStats();
            this.displayPapers();
            this.updatePagination();
            this.closeModal();
            
            // Показываем пустое состояние если нужно
            this.toggleEmptyState(this.allPapers.length === 0);
            
            tg.showAlert('Статья удалена из библиотеки');
            tg.HapticFeedback.notificationOccurred('success');
            
        } catch (error) {
            console.error('Ошибка удаления статьи:', error);
            tg.showAlert('Не удалось удалить статью');
            tg.HapticFeedback.notificationOccurred('error');
        }
    }
    
    changePage(newPage) {
        const totalPages = Math.ceil(this.filteredPapers.length / this.perPage);
        
        if (newPage < 1 || newPage > totalPages) return;
        
        this.currentPage = newPage;
        this.displayPapers();
        this.updatePagination();
        
        // Прокручиваем наверх
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    updatePagination() {
        const totalPages = Math.ceil(this.filteredPapers.length / this.perPage);
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        const pageInfo = document.getElementById('pageInfo');
        
        prevBtn.disabled = this.currentPage <= 1;
        nextBtn.disabled = this.currentPage >= totalPages;
        
        pageInfo.textContent = totalPages > 0 
            ? `Страница ${this.currentPage} из ${totalPages}`
            : 'Нет страниц';
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
    window.app = new LibraryApp();
});

// Обработка ошибок
window.addEventListener('error', (event) => {
    console.error('Глобальная ошибка:', event.error);
    tg.showAlert('Произошла ошибка в приложении');
});
