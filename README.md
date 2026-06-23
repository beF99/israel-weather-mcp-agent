# Israel Weather MCP Agent

## מטרת הפרויקט
הפרויקט מממש MCP Server ייעודי לתחזית מזג אוויר בישראל באמצעות Playwright, ללא שימוש ב-API מובנה.

המערכת כוללת:
1. `host.py` - צ'אט טרמינל שמפעיל LLM + Tools.
2. `weather_Israel.py` - MCP Server עם כלים לניווט באתר תחזית ישראלי, חיפוש עיר, בחירה ברשימה וחילוץ תוכן.
3. `weather_USA.py` - שרת דוגמה קיים לתחזית בארה"ב.

## סטאק טכנולוגי
1. Python
2. MCP SDK
3. Playwright
4. OpenAI API (Tool Calling)

## איך להריץ
להריץ מתוך תיקיית `project-template`:

```powershell
cd project-template
uv sync
uv run playwright install chromium
uv run host.py
```

## הגדרת משתני סביבה
יש ליצור/לעדכן קובץ `.env`:

```env
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4.1-mini
```

## דוגמאות שאלות שה-Agent יודע לענות
1. `מה התחזית בחיפה להיום?`
2. `מה מזג האוויר בבית שמש היום?`
3. `Are there active weather alerts in CA?`
4. `What is the forecast for New York City?`

## זרימת עבודה תמציתית
1. המשתמש שואל שאלה בטרמינל.
2. ה-Host שולח למודל את השאלה + רשימת tools.
3. המודל מפעיל tools לפי הצורך (open -> enter -> select -> extract).
4. תוצאות הכלים חוזרות למודל.
5. המודל מחזיר תשובה סופית למשתמש.

## הערות חשובות
1. אין להעלות את קובץ `.env` ל-Git.
2. הקובץ `.env.example` כולל רק תבנית ללא מפתחות.
3. תיתכנה תלות ברשת ובטעינת האתר בזמן אמת.
