import os
import re
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

# ============================================================
# Health server (for Render port binding)
# ============================================================
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
        self.wfile.write(b"Health Bot alive.")
    def do_HEAD(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), PingHandler).serve_forever()

# ============================================================
# Calculators
# ============================================================
def calc_bmi(height_cm: float, weight_kg: float):
    h_m = height_cm / 100
    bmi = weight_kg / (h_m ** 2)
    if bmi < 18.5: cat = "Underweight"
    elif bmi < 25: cat = "Normal weight"
    elif bmi < 30: cat = "Overweight"
    elif bmi < 35: cat = "Obese (Class I)"
    elif bmi < 40: cat = "Obese (Class II)"
    else: cat = "Obese (Class III)"
    return bmi, cat

def ideal_weight_range(height_cm: float):
    h_m = height_cm / 100
    return 18.5 * (h_m ** 2), 24.9 * (h_m ** 2)

def calc_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return bmr + (5 if gender == "male" else -161)

ACTIVITY_LEVELS = {
    "sedentary":   (1.2,   "Sedentary (little/no exercise)"),
    "light":       (1.375, "Light (1-3 days/week)"),
    "moderate":    (1.55,  "Moderate (3-5 days/week)"),
    "active":      (1.725, "Active (6-7 days/week)"),
    "very_active": (1.9,   "Very Active (athlete, 2x/day)"),
}

def calc_water(weight_kg: float) -> float:
    return weight_kg * 0.033  # liters/day

def heart_rate_zones(age: int):
    max_hr = 220 - age
    return {
        "max_hr": max_hr,
        "warm_up": (max_hr * 0.5, max_hr * 0.6),
        "fat_burn": (max_hr * 0.6, max_hr * 0.7),
        "cardio": (max_hr * 0.7, max_hr * 0.8),
        "peak": (max_hr * 0.8, max_hr * 0.9),
    }

def parse_numbers(text: str):
    parts = re.split(r"[\s,/]+", text.strip())
    return [p for p in parts if p]

# ============================================================
# Menus
# ============================================================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📏 BMI Calculator", callback_data="bmi")],
        [InlineKeyboardButton("🍔 Daily Calorie Needs", callback_data="calories")],
        [InlineKeyboardButton("💧 Water Intake", callback_data="water")],
        [InlineKeyboardButton("❤️ Heart Rate Zones", callback_data="hr")],
        [InlineKeyboardButton("💪 Ideal Weight", callback_data="ideal")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]])

def gender_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨 Male", callback_data="g_male"),
         InlineKeyboardButton("👩 Female", callback_data="g_female")],
    ])

def activity_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(desc, callback_data=f"a_{key}")]
        for key, (_, desc) in ACTIVITY_LEVELS.items()
    ])

# ============================================================
# Handlers
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❤️ *Health Calculator*\n\n"
        "BMI, calories, water intake, heart rate, ideal weight, all in one bot.\n\n"
        "_Estimates only. Consult a doctor for medical advice._\n\n"
        "Pick a tool:",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cb = query.data

    if cb == "home":
        context.user_data.clear()
        await query.edit_message_text(
            "❤️ *Health Calculator*\n\nPick a tool:",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        return

    if cb == "bmi":
        context.user_data["mode"] = "bmi"
        await query.edit_message_text(
            "📏 *BMI Calculator*\n\n"
            "Send your height (cm) and weight (kg), separated by space:\n\n"
            "Example: `170 70`\n_(170 cm tall, 70 kg)_",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "water":
        context.user_data["mode"] = "water"
        await query.edit_message_text(
            "💧 *Daily Water Intake*\n\n"
            "Send your weight in kg:\n\nExample: `70`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "hr":
        context.user_data["mode"] = "hr"
        await query.edit_message_text(
            "❤️ *Heart Rate Zones*\n\nSend your age:\n\nExample: `30`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "ideal":
        context.user_data["mode"] = "ideal"
        await query.edit_message_text(
            "💪 *Ideal Weight Range*\n\nSend your height in cm:\n\nExample: `170`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "calories":
        context.user_data["mode"] = "cal_gender"
        await query.edit_message_text(
            "🍔 *Daily Calorie Needs*\n\nStep 1 of 4: Select your gender",
            reply_markup=gender_menu(),
            parse_mode="Markdown",
        )
        return

    if cb.startswith("g_"):
        context.user_data["gender"] = cb.split("_", 1)[1]
        context.user_data["mode"] = "cal_stats"
        await query.edit_message_text(
            f"✅ Gender: {context.user_data['gender'].capitalize()}\n\n"
            "Step 2 of 4: Send your *age, weight (kg), height (cm)* on one line.\n\n"
            "Example: `30 70 175`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb.startswith("a_"):
        key = cb.split("_", 1)[1]
        u = context.user_data
        if not all(k in u for k in ("gender", "age", "weight", "height")):
            await query.edit_message_text("⚠️ Missing data. /start over.")
            u.clear()
            return
        bmr = calc_bmr(u["weight"], u["height"], u["age"], u["gender"])
        mult, desc = ACTIVITY_LEVELS[key]
        tdee = bmr * mult
        await query.edit_message_text(
            f"🍔 *Daily Calorie Needs*\n\n"
            f"Profile: {u['gender']}, {u['age']}y, {u['weight']}kg, {u['height']}cm\n"
            f"Activity: {desc}\n\n"
            f"📊 *BMR:* {bmr:,.0f} kcal/day\n"
            f"_(at complete rest)_\n\n"
            f"🍔 *TDEE:* *{tdee:,.0f} kcal/day*\n"
            f"_(total daily energy)_\n\n"
            f"Goals:\n"
            f"• 🔻 Lose 0.5 kg/week: *{tdee - 500:,.0f}* kcal\n"
            f"• ⚖️ Maintain: *{tdee:,.0f}* kcal\n"
            f"• 🔺 Gain 0.5 kg/week: *{tdee + 500:,.0f}* kcal",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        u.clear()
        return

    if cb == "help":
        await query.edit_message_text(
            "ℹ️ *How to use*\n\n"
            "All calculators use metric units (cm/kg).\n\n"
            "📏 *BMI* — Send `height_cm weight_kg`\n"
            "💧 *Water* — Send `weight_kg`\n"
            "❤️ *Heart Rate* — Send `age`\n"
            "💪 *Ideal Weight* — Send `height_cm`\n"
            "🍔 *Calories* — Guided 4-step flow\n\n"
            "_All calculations are local. Estimates only._",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()

    if mode == "bmi":
        try:
            nums = parse_numbers(text)
            if len(nums) != 2:
                raise ValueError
            h, w = float(nums[0]), float(nums[1])
            if not 50 <= h <= 250 or not 20 <= w <= 500:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Format: `<height_cm> <weight_kg>` (e.g. `170 70`)", parse_mode="Markdown")
            return
        bmi, cat = calc_bmi(h, w)
        low, high = ideal_weight_range(h)
        await update.message.reply_text(
            f"📏 *BMI Result*\n\n"
            f"Height: {h} cm  •  Weight: {w} kg\n\n"
            f"📊 *BMI: {bmi:.1f}*\n"
            f"Category: *{cat}*\n\n"
            f"_Healthy weight for your height: {low:.1f} – {high:.1f} kg_\n\n"
            f"BMI categories:\n"
            f"• <18.5 Underweight\n"
            f"• 18.5–24.9 Normal\n"
            f"• 25–29.9 Overweight\n"
            f"• 30+ Obese",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    if mode == "water":
        try:
            w = float(text)
            if not 20 <= w <= 500:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Send your weight in kg (e.g. `70`)")
            return
        liters = calc_water(w)
        glasses = liters / 0.25
        await update.message.reply_text(
            f"💧 *Daily Water Intake*\n\n"
            f"Weight: {w} kg\n\n"
            f"💧 *{liters:.2f} L/day*\n"
            f"≈ {glasses:.0f} glasses (250 ml each)\n\n"
            f"_Add 0.5–1 L if you exercise or live in a hot climate._",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    if mode == "hr":
        try:
            age = int(text)
            if not 5 <= age <= 120:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Send your age (e.g. `30`)")
            return
        z = heart_rate_zones(age)
        await update.message.reply_text(
            f"❤️ *Heart Rate Zones*\n\n"
            f"Age: {age}  •  Max HR: *{z['max_hr']} bpm*\n\n"
            f"💤 Rest: 50–60 bpm\n"
            f"🚶 Warm-up: {z['warm_up'][0]:.0f}–{z['warm_up'][1]:.0f} bpm\n"
            f"🔥 Fat Burn: {z['fat_burn'][0]:.0f}–{z['fat_burn'][1]:.0f} bpm\n"
            f"💪 Cardio: {z['cardio'][0]:.0f}–{z['cardio'][1]:.0f} bpm\n"
            f"🚀 Peak: {z['peak'][0]:.0f}–{z['peak'][1]:.0f} bpm",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    if mode == "ideal":
        try:
            h = float(text)
            if not 50 <= h <= 250:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Send your height in cm (e.g. `170`)")
            return
        low, high = ideal_weight_range(h)
        await update.message.reply_text(
            f"💪 *Ideal Weight Range*\n\n"
            f"Height: {h} cm\n\n"
            f"💪 *{low:.1f} – {high:.1f} kg*\n\n"
            f"_Based on BMI 18.5–24.9 (the 'normal' range)._",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    if mode == "cal_stats":
        nums = parse_numbers(text)
        if len(nums) != 3:
            await update.message.reply_text("⚠️ Send 3 numbers: age, weight (kg), height (cm). e.g. `30 70 175`")
            return
        try:
            age = int(nums[0])
            weight = float(nums[1])
            height = float(nums[2])
            if not 5 <= age <= 120 or not 20 <= weight <= 500 or not 50 <= height <= 250:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Invalid values. Format: `age weight_kg height_cm`")
            return
        context.user_data["age"] = age
        context.user_data["weight"] = weight
        context.user_data["height"] = height
        context.user_data["mode"] = "cal_activity"
        await update.message.reply_text(
            f"✅ Age: {age}  •  Weight: {weight} kg  •  Height: {height} cm\n\n"
            "Step 3 of 4: Select your activity level",
            reply_markup=activity_menu(),
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("Tap a button to use a tool. /start", reply_markup=main_menu())

# ============================================================
# Main
# ============================================================
def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        log.critical("BOT_TOKEN env var missing!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Health Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
