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
        document.getElementById('tagFilter').addEventListener('change', (e) => {
            this.handletagFilter(e.target.value);
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
            if (this.currentPaper) {
                this.deletePaper(this.currentPaper.external_id);
            }
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
    
    async loadLibrary(searchQuery = '') {
        this.showLoading(true);
        try {
            const url = new URL('/api/v1/library', window.location.origin);
            url.searchParams.append('page', '1');
            url.searchParams.append('per_page', '1000'); // Загружаем все статьи для клиентской фильтрации
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
            this.displayPapers();
            this.updatePagination();
            
            this.toggleEmptyState(this.totalPapers === 0);

        } catch (error) {
            this.showError(`Ошибка загрузки библиотеки: ${error.message}`);
            this.toggleEmptyState(true);
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
    
    handleSearch(query) {
        const searchTerm = query.toLowerCase().trim();
        
        if (!searchTerm) {
            this.filteredPapers = [...this.allPapers];
        } else {
            this.filteredPapers = this.allPapers.filter(paper => 
                paper.title.toLowerCase().includes(searchTerm) ||
                paper.authors.join(', ').toLowerCase().includes(searchTerm) ||
                paper.abstract.toLowerCase().includes(searchTerm)
            );
        }
        
        this.currentPage = 1;
        this.displayPapers();
        this.updatePagination();
    }
    
    handletagFilter(tag) {
        if (!tag) {
            this.filteredPapers = [...this.allPapers];
        } else {
            this.filteredPapers = this.allPapers.filter(paper => 
                paper.tags && paper.tags.includes(tag)
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
        
        const tagsHtml = paper.tags 
            ? paper.tags.map(tag => `<span class="category-tag">${tag}</span>`).join('')
            : '';
        
        const publishedDate = paper.publication_date 
            ? new Date(paper.publication_date).toLocaleDateString('ru-RU')
            : 'Дата не указана';
        
        const savedDate = paper.saved_at 
            ? new Date(paper.saved_at).toLocaleDateString('ru-RU')
            : '';
            
        card.innerHTML = `
            <h3 class="paper-title">${this.escapeHtml(paper.title)}</h3>
            <div class="paper-authors">${this.escapeHtml(paper.authors)}</div>
            <div class="paper-meta">
                <span class="paper-date">📅 ${publishedDate}</span>
                <div class="paper-tags">${tagsHtml}</div>
            </div>
            <p class="paper-abstract">${this.escapeHtml(this.truncateText(paper.abstract, 200))}</p>
            <div class="paper-actions" onclick="event.stopPropagation();">
                <button class="action-btn view-btn">
                    👁 Подробнее
                </button>
                <button class="action-btn delete-btn">
                    🗑 Удалить
                </button>
            </div>
        `;
        
        // Add event listeners programmatically
        const viewBtn = card.querySelector('.view-btn');
        const deleteBtn = card.querySelector('.delete-btn');
        
        viewBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openPaperModal(paper);
        });
        
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.deletePaper(paper.external_id);
        });
        
        return card;
    }
    
    openPaperModal(paper) {
        this.currentPaper = paper;
        const modal = document.getElementById('paperModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalBody = document.getElementById('modalBody');
        
        modalTitle.textContent = paper.title;

        const publishedDate = paper.publication_date
            ? new Date(paper.publication_date).toLocaleDateString('ru-RU')
            : 'Дата не указана';
            
        const tagsHtml = paper.tags 
            ? paper.tags.map(cat => `<span class="category-tag">${cat}</span>`).join('')
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
                <strong>Категории:</strong>
                <button id="editTagsBtn" class="action-btn" style="margin-left: 8px; padding: 2px 6px; font-size: 12px;">✏️</button>
                <br>
                <div style="margin-top: 8px;">${tagsHtml}</div>
            </div>
            
            <div style="margin-bottom: 16px;">
                <strong>Аннотация:</strong><br>
                <p style="margin-top: 8px; line-height: 1.6;">${paper.abstract}</p>
            </div>
            
            ${paper.external_id ? `<div style="margin-bottom: 16px;">
                <strong>${paper.source} ID:</strong> ${paper.external_id}
            </div>` : ''}
        `;
        
        modal.classList.add('visible');
        
        // Remove any existing event listener to prevent multiple bindings
        const editBtn = document.getElementById('editTagsBtn');
        editBtn.replaceWith(editBtn.cloneNode(true));
        
        // Add event listener for the edit tags button
        document.getElementById('editTagsBtn').addEventListener('click', () => this.editTags());
        
        // Haptic feedback
        tg.HapticFeedback.impactOccurred('medium');
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
            tg.HapticFeedback.notificationOccurred('success');
            
        } catch (error) {
            console.error('Ошибка удаления статьи:', error);
            tg.showAlert('Не удалось удалить статью');
            tg.HapticFeedback.notificationOccurred('error');
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
