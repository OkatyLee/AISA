from database import SQLDatabase as db
from services import ArxivSearcher
from utils import create_paper_keyboard
from utils.error_handler import ErrorHandler
from utils.metrics import track_operation
from aiogram.types import CallbackQuery
from aiogram import types
from aiogram import Dispatcher
from utils import setup_logger

logger = setup_logger(
    name="library_logger",
    level="INFO"
)


def register_library_handlers(dp: Dispatcher):
    dp.callback_query.register(
        handle_save_paper,
        lambda c: c.data.startswith("save_paper:")
    )
    
    dp.callback_query.register(
        handle_delete_paper,
        lambda c: c.data.startswith("delete_paper:")
    )
    
    
    dp.callback_query.register(
        handle_library_stats,
        lambda c: c.data == "library_stats"
    )
    
    dp.callback_query.register(
        handle_export_bibtex,
        lambda c: c.data == "export_bibtex"
    )

@track_operation("save_paper")
async def handle_save_paper(callback: CallbackQuery):
    try:
        paper_url = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id
        async with ArxivSearcher() as searcher:
            paper = await searcher.get_paper_by_url(paper_url)
        success = await db.save_paper(user_id, paper)  
        if success:
            await callback.message.edit_reply_markup(
                reply_markup=create_paper_keyboard(
                    paper, user_id, is_saved=True
                ).as_markup()
            )
            await callback.answer("✅ Статья сохранена в библиотеку!")
        else:
            await callback.answer("❌ Статья уже сохранена в библиотеке")
            
    except Exception as e:
        await callback.answer(f"❌ Ошибка при сохранении: {str(e)}") 
        
@track_operation("delete_paper")
async def handle_delete_paper(callback: CallbackQuery):
    try:
        paper_url = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id
        
        library = await db.get_user_library(user_id)
        paper_to_remove = None
        for paper in library:
            if paper['url'] == paper_url:
                paper_to_remove = paper
                break
        if paper_to_remove:
            success = await db.delete_paper(user_id, paper_to_remove['id'])

            if success:
                await callback.message.edit_reply_markup(
                    reply_markup=create_paper_keyboard(
                        paper_to_remove, user_id, is_saved=False
                    ).as_markup()
                )
                await callback.answer("✅ Статья удалена из библиотеки!")
            else:
                await callback.answer("❌ Ошибка при удалении статьи")  
    except Exception as e:
        await callback.answer(f"❌ Ошибка при удалении: {str(e)}")
        
        
async def handle_library_status(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        stats = await db.get_library_status(user_id)        
        stats_message = f"""📊 Статистика вашей библиотеки:

            📚 Всего статей: {stats['total_papers']}
            🆕 За последний месяц: {stats['recent_papers']}

            🏷️ Популярные теги:"""
        
        for tag, count in stats['popular_tags'][:5]:
            stats_message += f"\n• {tag}: {count}"
        
        if not stats['popular_tags']:
            stats_message += "\n• Теги не добавлены"
        
        await callback.message.answer(stats_message)
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка при получении статистики: {str(e)}")
        
async def handle_library_stats(callback: CallbackQuery):
    """Обработчик показа статистики библиотеки"""
    try:
        user_id = callback.from_user.id
        stats = await db.get_library_stats(user_id)
        
        stats_message = f"""📊 Статистика вашей библиотеки:

📚 Всего статей: {stats['total_papers']}
🆕 За последний месяц: {stats['recent_papers']}

🏷️ Популярные теги:"""
        
        for tag, count in stats['popular_tags'][:5]:
            stats_message += f"\n• {tag}: {count}"
        
        if not stats['popular_tags']:
            stats_message += "\n• Теги не добавлены"
        
        await callback.message.answer(stats_message)
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка при получении статистики: {str(e)}")

async def handle_export_bibtex(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        bibtex_content = await db.export_library_bibtex(user_id)
        
        if bibtex_content:
            with open(f"library_{user_id}.bib", "w", encoding="utf-8") as f:
                f.write(bibtex_content)
            
            with open(f"library_{user_id}.bib", "rb") as f:
                await callback.message.answer_document(
                    document=types.BufferedInputFile(
                        f.read(),
                        filename=f"library_{user_id}.bib"
                    ),
                    caption="📁 Ваша библиотека в формате BibTeX"
                )
            
            await callback.answer("✅ Файл отправлен!")
        else:
            await callback.answer("❌ Библиотека пуста")
            
    except Exception as e:
        await callback.answer(f"❌ Ошибка при экспорте: {str(e)}")