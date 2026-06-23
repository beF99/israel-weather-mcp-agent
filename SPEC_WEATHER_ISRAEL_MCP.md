# SPEC + תוכנית ביצוע: Weather MCP Israel (Playwright)

## תקציר
המטרה היא לבנות MCP Server ייעודי לתחזית מזג אוויר בישראל, ללא API מובנה, באמצעות אוטומציית דפדפן עם Playwright מול האתר:

`https://www.weather2day.co.il/forecast`

השרת יחשוף Tools ל-LLM כך שיוכל:
1. לפתוח את עמוד התחזית.
2. להזין עיר לחיפוש.
3. לבחור עיר מהרשימה.
4. לחלץ את תוכן הדף ולהחזיר תשובה טקסטואלית מועשרת לצ'אט.

---

## מטרות לימודיות
1. מימוש MCP Server עצמאי מקצה לקצה.
2. שילוב Playwright כיכולת פעולה בדפדפן עבור LLM.
3. בניית רצף Tool Calling רב-שלבי (open -> type -> select -> extract).
4. אספקת קונטקסט טקסטואלי ל-LLM לצורך תשובה סופית בשיחה (RAG-like).

---

## תחום המטלה
### In Scope
1. מימוש `weather_Israel.py` כשרת MCP פעיל.
2. הוספת השרת לרשימת שרתי MCP ב-`host.py`.
3. מימוש 4 Tools:
   1. `open_weather_forecast_israel`
   2. `enter_weather_forecast_city_israel`
   3. `select_weather_forecast_city_israel`
   4. `extract_weather_forecast_content_israel`
4. תמיכה בזרימת עבודה מלאה מתוך צ'אט טרמינל.

### Out of Scope
1. בניית UI גרפי משלנו.
2. תמיכה רשמית בכל אתרי מזג האוויר.
3. עקיפת Captcha או אנטי-בוט אגרסיבי.

---

## מצב קיים בריפו
1. `project-template/weather_Israel.py` קיים כשלד בלבד.
2. `project-template/weather_USA.py` ממומש ומשמש רפרנס למבנה MCP Tool.
3. `project-template/host.py` מנהל את האינטראקציה בין LLM לכלי MCP.
4. `pyproject.toml` כבר כולל `playwright`.

---

## תכנון ארכיטקטורה
### רכיבים
1. `host.py`
   1. מגדיר אילו שרתי MCP זמינים.
   2. שולח למודל את רשימת הכלים.
   3. מפעיל כלי לפי בקשת המודל ומחזיר תוצאות.
2. `weather_Israel.py`
   1. מחזיק את הלוגיקה לדפדפן (Playwright).
   2. חושף Tools דרך `@mcp.tool()`.
   3. שומר state של דפדפן פתוח בין קריאות.

### מצב דפדפן (State)
1. נשמור ברמת מודול:
   1. `playwright` instance
   2. `browser`
   3. `context`
   4. `page`
2. כל Tool יבדוק שה-session קיים לפני פעולה.
3. אם אין state מוכן, נחזיר הודעת שגיאה ידידותית עם הנחיה להפעיל קודם כלי פתיחה.

---

## API של הכלים (חוזה התנהגות)
## 1) `open_weather_forecast_israel() -> str`
### אחריות
1. להפעיל Chromium.
2. לפתוח לשונית חדשה.
3. לנווט ל-`/forecast`.
4. להמתין לטעינה ראשונית.

### פלט צפוי
טקסט הצלחה כמו:
`"Weather Israel page opened successfully."`

## 2) `enter_weather_forecast_city_israel(city: str) -> str`
### אחריות
1. לאתר את שדה החיפוש.
2. לנקות שדה קיים.
3. להזין את שם העיר.
4. להמתין להופעת dropdown.

### פלט צפוי
טקסט כמו:
`"City typed successfully: Tel Aviv"`

## 3) `select_weather_forecast_city_israel() -> str`
### אחריות
1. לבחור את הפריט הראשון ברשימת ההצעות.
2. להמתין לניווט/עדכון דף תחזית עיר.

### פלט צפוי
טקסט כמו:
`"First city option selected successfully."`

## 4) `extract_weather_forecast_content_israel() -> str`
### אחריות
1. לחלץ טקסט רלוונטי מאזור התחזית.
2. לבצע ניקוי בסיסי:
   1. הסרת whitespace כפול.
   2. הסרת תפריטים/טקסט ניווט אם צריך.
3. להגביל אורך סביר לקונטקסט (למשל 4,000-8,000 תווים).

### פלט צפוי
טקסט נקי שניתן להעביר ל-LLM כדי שינסח תשובה.

---

## פרטי מימוש מומלצים ב-Playwright
1. שימוש ב-`async_playwright()`.
2. שימוש ב-`browser.new_context()` במקום page בודד ללא context.
3. המתנות יציבות:
   1. `page.goto(..., wait_until="domcontentloaded")`
   2. `page.wait_for_selector(...)`
4. איתור אלמנטים:
   1. קודם selectors יציבים ככל האפשר.
   2. fallback selectors במקרה שה-DOM משתנה.
5. טיפול שגיאות:
   1. `PlaywrightTimeout`
   2. שגיאות איתור אלמנט
   3. החזרת הודעות שגיאה ידידותיות במקום קריסה.

---

## שינויי קוד נדרשים
1. `project-template/weather_Israel.py`
   1. מימוש state גלובלי לדפדפן.
   2. מימוש 4 הכלים.
   3. פונקציות עזר פנימיות:
      1. `ensure_browser_session`
      2. `safe_close_browser` (אופציונלי)
      3. `clean_text` לניקוי פלט.
2. `project-template/host.py`
   1. עדכון רשימת `self.mcp_clients` כך שתכלול גם:
      1. `MCPClient("./weather_Israel.py")`
3. אופציונלי: `project-template/README.md`
   1. הוראות הרצה ודוגמאות שאילתא.

---

## שלבי ביצוע (Execution Plan)
## שלב 0: הכנה
1. `uv sync`
2. `uv run playwright install chromium`
3. `uv run host.py`
4. בדיקת sanity מול `weather_USA.py`.

## שלב 1: Tools תפעול דפדפן
1. לממש `open_weather_forecast_israel`.
2. לממש `enter_weather_forecast_city_israel`.
3. לממש `select_weather_forecast_city_israel`.
4. לחבר את `weather_Israel.py` ל-`host.py`.
5. לבדוק ידנית ש-LLM מפעיל את שלושת הכלים ברצף נכון.

## שלב 2: חילוץ תוכן ותשובה מלאה
1. לממש `extract_weather_forecast_content_israel`.
2. לוודא שה-LLM מקבל טקסט תחזית משמעותי.
3. לוודא שהתשובה למשתמש ניתנת ישירות בצ'אט.

## שלב 3: הקשחה
1. שיפור הודעות שגיאה למקרי timeout.
2. שיפור selectors עם fallback.
3. מניעת זליגות משאבים (סגירה נקייה בסיום).

---

## קריטריוני קבלה (Acceptance Criteria)
1. שאילתה כמו:
   1. `"מה התחזית בתל אביב?"`
   מפעילה רצף כלים מלא ומחזירה תשובה סופית בצ'אט.
2. אם לא נמצאה עיר:
   1. מתקבלת הודעת שגיאה מובנת ולא traceback.
3. ה-Host מזהה ומציג לפחות שני שרתי MCP:
   1. USA
   2. Israel
4. לאחר `quit` אין תהליך דפדפן תקוע.

---

## תרחישי בדיקה ידניים
1. תחזית לעיר מרכזית:
   1. תל אביב
   2. ירושלים
2. תחזית לעיר עם איות חלופי:
   1. באר שבע / באר-שבע
3. קלט שגוי:
   1. `"עירלאקיימת123"`
4. ריבוי שאילתות ברצף באותה ריצה:
   1. תל אביב
   2. חיפה
   3. אילת

---

## ניהול סיכונים
1. שינוי DOM באתר היעד:
   1. פתרון: selectors חלופיים + הודעת כשל ברורה.
2. timeout בגלל רשת/סינון:
   1. פתרון: timeouts ארוכים יותר ו-retry עדין.
3. פתיחת דפדפן מרובה:
   1. פתרון: session יחיד שנשמר ונעשה בו reuse.

---

## פקודות הרצה
מתוך `project-template`:

```powershell
uv sync
uv run playwright install chromium
uv run host.py
```

דוגמת שאילתא:

```text
מה התחזית להיום בתל אביב?
```

---

## Definition of Done
1. `weather_Israel.py` ממומש עם 4 Tools פעילים.
2. `host.py` מחובר לשרת ישראל.
3. ניתן לקבל תשובה מלאה בצ'אט עבור לפחות 3 ערים בישראל.
4. קיימות הודעות שגיאה ידידותיות למצבי כשל.
5. יש תיעוד הרצה קצר וברור.

