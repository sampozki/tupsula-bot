#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import configparser
import requests
import datetime
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import os
import csv
import random


DATA_URL = "https://api.thingspeak.com/channels/1068855/fields/1.csv"

NAKKIKAMPPAE_STRING = """<b>{} Nakkikämppävuoro</b>

Ohje:
- Selvitä kaljatilanne
- Pese vieraspyyhkeet
- Osta pyykin- ja astianpesuainetta
- Osta vessapaperia ja käsisaippuaa
- Tyhjennä roskikset ja osta pusseja
- Pahvit/Lasit/Metallit keräyksiin
- Tölkit kauppaan"""

SURKULIST = ["😟", "😟😟😟", "😔", "😔😔", "😢😢", "😭", ":(", ":(((", ":sadge:"]

SAUNAWARMLIST = ["Saunassa ompi yli 70°C",
                 "Saunassa ompi yli 70°C",
                 "Saunassa ompi yli 70°C",
                 "Saunassa yli 70°C, meikä poika: nonniih",
                 "Yli 70°C lämmintä, kaikki teletapit saunaan",
                 "Yli 70°C, hiki tulee jo pelkästä ajatuksesta",
                 "🔥 70°C ja mä oon ihan 🐒🧠 rn",
                 "Skipidi sauna, yli 70°C skkrt",
                 "Saunassa nyt +70°C, huutokauppakeisari sanois: KAU-HOTTA!",
                 "It's sauna o clock +70°C"]

#--------------- CODE BELOW ---------------

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__) 

config = configparser.ConfigParser()

sauna_warm_sent = False

try:
    # Read env
    GROUP_ID = os.getenv("GROUP_ID")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
except:
    logger.error("You must assign GROUP_ID and BOT_TOKEN in config.ini source file.")
    exit()


# ----- nakkikämppähirvitys -----

# Returns weeks since specified date + default offset
def weeks_since_start(date1):
    NAKKIKAMPPAE_OFFSET = 4 # Offset to account for current nakkikämppä turn
    STARTDATE = datetime.date(2021, 1, 4) # First monday of 2021

    # Mondays of weeks
    monday1 = (STARTDATE - datetime.timedelta(days=STARTDATE.weekday()))
    monday2 = (date1 - datetime.timedelta(days=date1.weekday()))
    
    # Return number of weeks
    return ((monday2 - monday1).days / 7) + NAKKIKAMPPAE_OFFSET


# Return current nakkikämppä as string
def nakkikamppae():
    kamppa_number = int((weeks_since_start(datetime.date.today()) % 21) + 1)
    
    # Concat letter
    if(kamppa_number <= 9):
        return "A" + str(kamppa_number)
    else:
        return "B" + str(kamppa_number)


# Cron function that sends the nakkikämppämessage
def nakkikamppa_info(context):
    logger.info("Nakkikamppainfo lähetetty")
    context.bot.send_message(chat_id=GROUP_ID, text=NAKKIKAMPPAE_STRING.format(nakkikamppae()), parse_mode=telegram.ParseMode.HTML)


# ----- saunapaska -----

def _safe_float(s):
    try:
        return float(s)
    except:
        return None


def get_sauna_temps():
    try:
        r = requests.get(DATA_URL, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Virhe datan haussa: {e}")
        return None

    reader = csv.reader(r.text.splitlines())
    header = next(reader, None)  # skip header if present

    rows = [row for row in reader if len(row) >= 3 and row[2].strip()]
    if not rows:
        return None

    # latest row
    ts_raw, _, temp_raw = rows[-1]
    try:
        latest_ts = datetime.datetime.strptime(ts_raw.strip(), "%Y-%m-%d %H:%M:%S UTC")
        latest_ts = latest_ts.replace(tzinfo=datetime.timezone.utc)
        latest_temp = float(temp_raw.strip())
    except Exception as e:
        print(f"Virhe rivin jäsentämisessä: {e}")
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    is_stale = (now - latest_ts) > datetime.timedelta(minutes=60)

    temps_f = [_safe_float(r[2].strip()) for r in rows if len(r) >= 3 and r[2].strip()]
    temps_f = [t for t in temps_f if t is not None]
    trend = "tasainen"
    if len(temps_f) >= 6:
        delta = temps_f[-1] - temps_f[-6]
    elif len(temps_f) >= 2:
        delta = temps_f[-1] - temps_f[-2]
    else:
        delta = 0.0

    if delta > 1.0:
        trend = "nouseva"
    elif delta < -0.5:
        trend = "laskeva"

    return latest_temp, trend, is_stale


def sauna_warm_poller(context):
    try:
        result = get_sauna_temps()
        if result is None:
            logger.error("Lämpötilaa ei saa haettua!")
            return
        latest_temp, trend, is_stale = result
    except Exception as e:
        logger.error(f"Lämpötilaa ei saa haettua! ({e})")
        return

    if is_stale:
        logger.info("Data on yli 60 min vanha. Ilmoitusta ei lähetetä.")
        return

    already_sent = bool(getattr(context.job, "context", False))

    if latest_temp > 70 and not already_sent:
        context.job.context = True
        context.bot.send_message(
            chat_id=GROUP_ID,
            text=str(random.choice(SAUNAWARMLIST)),
            parse_mode=telegram.ParseMode.HTML
        )
    elif latest_temp < 65 and already_sent:
        context.job.context = False


def sauna(update, context):
    logger.info("/sauna: " + str(update.message.chat))

    result = get_sauna_temps()
    if result is None:
        update.message.reply_text("Lämpötilaa ei saatu haettua!")
        return

    latest_temp, trend, is_stale = result

    reply = f"Saunan lämpötila on {latest_temp:.1f}°C {trend}"
    if is_stale:
        reply += ". Viimeisin lämpödata yli tunnin vanha "+str(random.choice(SURKULIST))

    update.message.reply_text(reply)


# ----- random paska -----

def error(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    
def echo(update, context):
    logger.info("Message: " + update.message.text)

def unpin(update, context):
    logger.info(update.message.sender_chat)
    if(update.message.sender_chat != None and update.message.sender_chat.type=="channel"):
        context.bot.unpin_chat_message(chat_id=update.message.chat_id, message_id=update.message.message_id)


# ----- maini -----

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    
    # Set nakkikämppä info to be sent at ~12:00 on Mon
    job_queue = updater.job_queue
    job_queue.run_daily(nakkikamppa_info, days=[0], time=datetime.time(hour=10, minute=00, second=00))
    job_queue.run_repeating(sauna_warm_poller, 60, first=0, context=False)

    dp = updater.dispatcher
    
    # Command handlers
    dp.add_handler(CommandHandler("sauna", sauna))
    dp.add_handler(MessageHandler(Filters.text, unpin))

    dp.add_error_handler(error)
    updater.start_polling()

    updater.idle()

if __name__ == '__main__':
    main()
