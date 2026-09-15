"""haqdaar/voice_demo.py — fixed (rigged) voice demo call, Hindi or English (15 Sep).

The caller SPEAKS (or presses keys). Sarvam voice speaks every line; all lines are
rendered before the call. Sarvam speech-to-text hears the caller; if it is slow or
unsure, the call follows the script's default answer, so the demo never gets stuck.
Facts are from the 3 real farmer schemes in data_cache (myscheme.gov.in).

    make run-demo      (tunnel + this server + rings CALL_ME_NUMBER)
Step 1's server.py and the keypad demo_server.py are untouched. One caller at a time.
"""
from __future__ import annotations

import asyncio
import audioop
import base64
import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

from haqdaar.audio.telephony import (
    DtmfEvent, MarkEvent, MediaEvent, StartEvent, StopEvent,
    build_clear, build_mark, build_media, build_stream_twiml, parse_event,
)
from haqdaar.demo_voice import render_ulaw as mac_render

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SPEAKER = "priya"
TTS_LANG = {"hi": "hi-IN", "en": "en-IN"}
CACHE = Path(__file__).resolve().parent / "voice_demo_clips"  # committed: works with no Sarvam credits
STT_WAIT = 4.5          # s; slower than this -> use the script's default answer
NO_SPEECH_WAIT = 7.0    # s of silence before "sorry, say again"
CHUNK = 8000            # 1 s of mu-law per media message

# ---- the script -------------------------------------------------------------
# Buttons pick the type of help (small menu for now). Speech works too, but anything
# heard by voice is read back for a 1/2 confirm, because phone speech-to-text mishears
# single words (15 Sep: "pension" came back as "वे नवाद कर दो").
GREET = ("नमस्ते! हक़दार में आपका स्वागत है। हिंदी में बात करने के लिए हिंदी बोलिए, या एक दबाइए। "
         "For English, say English, or press two.")

LINES: dict[str, dict[str, str]] = {
    "hi": {
        # menus and confirmations
        "need_menu": "मैं सरकारी योजनाओं में आपकी मदद करूँगी। आपको किस चीज़ में मदद चाहिए? खेती के लिए 1 दबाइए। पेंशन के लिए 2। इलाज के लिए 3। रोज़गार के लिए 4।",
        "conf_farm": "आपने खेती चुनी। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_pension": "आपने पेंशन चुनी। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_health": "आपने इलाज चुना। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_jobs": "आपने रोज़गार चुना। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_yes": "आपने हाँ कहा। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_no": "आपने ना कहा। सही है तो 1 दबाइए, नहीं तो 2।",
        "not_understood": "माफ़ कीजिए, मैं समझ नहीं पाई। कृपया बटन दबाइए।",
        "try_keys": "ठीक है। कृपया बटन दबाकर चुनिए।",
        "wrong_key": "यह बटन इस सवाल के लिए नहीं है।",
        "yn_keys": "माफ़ कीजिए। हाँ के लिए 1 दबाइए, ना के लिए 2।",
        "sorry": "माफ़ कीजिए, मैं सुन नहीं पाई। एक बार फिर।",
        # farming
        "farm_ack": "ठीक है, खेती से जुड़ी योजनाएँ। सही योजना ढूँढने के लिए मैं आपसे दो छोटे सवाल पूछूँगी।",
        "q_land": "पहला सवाल। क्या खेती की ज़मीन आपके अपने नाम पर है? हाँ के लिए 1, ना के लिए 2 दबाइए।",
        "q_loan": "दूसरा सवाल। क्या आपको खेती के लिए लोन की ज़रूरत है? हाँ के लिए 1, ना के लिए 2।",
        "res_yy": "आपके लिए तीन योजनाएँ मिली हैं। पहली, प्रधानमंत्री किसान सम्मान निधि, इसमें हर साल छह हज़ार रुपये मिलते हैं। दूसरी, किसान क्रेडिट कार्ड, खेती के लिए लोन। तीसरी, प्रधानमंत्री फसल बीमा योजना, कम प्रीमियम पर फसल का बीमा।",
        "res_yn": "आपके लिए दो योजनाएँ मिली हैं। पहली, प्रधानमंत्री किसान सम्मान निधि, इसमें हर साल छह हज़ार रुपये मिलते हैं। दूसरी, प्रधानमंत्री फसल बीमा योजना, कम प्रीमियम पर फसल का बीमा।",
        "res_ny": "ज़मीन आपके नाम पर नहीं है, इसलिए किसान सम्मान निधि नहीं मिलेगी। लेकिन दो योजनाएँ आपके लिए हैं, जो बटाईदार और किराए पर खेती करने वाले किसान भी ले सकते हैं। पहली, किसान क्रेडिट कार्ड, खेती के लिए लोन। दूसरी, प्रधानमंत्री फसल बीमा योजना।",
        "res_nn": "ज़मीन आपके नाम पर नहीं है, इसलिए किसान सम्मान निधि नहीं मिलेगी। लेकिन प्रधानमंत्री फसल बीमा योजना आपके लिए है। बटाईदार और किराए पर खेती करने वाले किसान भी इसे ले सकते हैं।",
        "which_yy": "किस योजना के बारे में और जानना चाहेंगे? किसान सम्मान निधि के लिए 1 दबाइए। किसान क्रेडिट कार्ड के लिए 2। फसल बीमा के लिए 3।",
        "which_yn": "किस योजना के बारे में और जानना चाहेंगे? किसान सम्मान निधि के लिए 1 दबाइए। फसल बीमा के लिए 2।",
        "which_ny": "किस योजना के बारे में और जानना चाहेंगे? किसान क्रेडिट कार्ड के लिए 1 दबाइए। फसल बीमा के लिए 2।",
        "conf_pmkisan": "आपने किसान सम्मान निधि चुनी। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_kcc": "आपने किसान क्रेडिट कार्ड चुना। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_pmfby": "आपने फसल बीमा चुना। सही है तो 1 दबाइए, नहीं तो 2।",
        "detail_pmkisan": "प्रधानमंत्री किसान सम्मान निधि। सरकारी वेबसाइट के अनुसार, हर पात्र किसान परिवार को साल में छह हज़ार रुपये मिलते हैं, दो-दो हज़ार की तीन किस्तों में, हर चार महीने पर। इसके लिए आधार कार्ड, ज़मीन के कागज़ और बैंक खाता चाहिए।",
        "detail_kcc": "किसान क्रेडिट कार्ड। सरकारी वेबसाइट के अनुसार, इससे फसल उगाने, कटाई के बाद के खर्च और खेती के सामान की मरम्मत के लिए लोन मिलता है। बटाईदार और किराए के किसान भी इसे ले सकते हैं। इसके लिए आवेदन फ़ॉर्म, दो फ़ोटो, आधार या वोटर कार्ड, और ज़मीन के कागज़ चाहिए।",
        "detail_pmfby": "प्रधानमंत्री फसल बीमा योजना। सरकारी वेबसाइट के अनुसार, खरीफ़ फसल पर किसान को सिर्फ़ दो प्रतिशत प्रीमियम देना होता है, और रबी फसल पर डेढ़ प्रतिशत। बाकी प्रीमियम सरकार देती है। सूखा, बाढ़, कीड़े और बीमारी से हुए नुकसान का बीमा होता है।",
        "apply_pmkisan": "आवेदन का तरीका। पीएम किसान पोर्टल पर जाइए, या नज़दीकी जन सेवा केंद्र पर। न्यू फार्मर रजिस्ट्रेशन चुनिए, आधार नंबर और मोबाइल नंबर डालिए, ओटीपी डालिए, जानकारी भरिए, कागज़ अपलोड कीजिए और सबमिट कीजिए।",
        "apply_kcc": "आवेदन का तरीका। जिस बैंक से कार्ड लेना है, उसकी वेबसाइट पर या बैंक शाखा में जाइए। किसान क्रेडिट कार्ड चुनिए, फ़ॉर्म भरिए और सबमिट कीजिए। अगर आप पात्र हैं, तो बैंक तीन-चार कामकाजी दिनों में आपसे संपर्क करेगा।",
        "apply_pmfby": "आवेदन का तरीका। प्रधानमंत्री फसल बीमा योजना की वेबसाइट पर, या नज़दीकी जन सेवा केंद्र पर जाइए। फार्मर कॉर्नर में रजिस्ट्रेशन फ़ॉर्म भरिए। ज़मीन के कागज़, बैंक पासबुक और बोई गई फसल की जानकारी दीजिए। बुवाई शुरू होने के दो हफ़्ते के अंदर आवेदन करना होता है।",
        # pension
        "pension_ack": "ठीक है, पेंशन। मैं आपसे दो छोटे सवाल पूछूँगी।",
        "q_age": "पहला सवाल। क्या आपकी उम्र अठारह से चालीस साल के बीच है? हाँ के लिए 1, ना के लिए 2।",
        "q_account": "दूसरा सवाल। क्या आपका बैंक या पोस्ट ऑफिस में बचत खाता है? हाँ के लिए 1, ना के लिए 2।",
        "pension_ok": "अच्छी खबर। आप अटल पेंशन योजना में जुड़ सकते हैं।",
        "pension_no_account": "अटल पेंशन योजना के लिए बैंक या पोस्ट ऑफिस में बचत खाता ज़रूरी है, क्योंकि हर महीने का पैसा उसी से कटता है। पहले खाता खुलवाइए। अब योजना के बारे में सुनिए।",
        "pension_too_old": "अटल पेंशन योजना में अठारह से चालीस साल की उम्र में ही जुड़ सकते हैं। अभी मेरी सूची में आपकी उम्र के लिए पेंशन की कोई दूसरी योजना नहीं है।",
        "detail_apy": "अटल पेंशन योजना। सरकारी वेबसाइट के अनुसार, साठ साल की उम्र के बाद जीवन भर हर महीने पक्की पेंशन मिलती है, एक हज़ार से पाँच हज़ार रुपये तक। आपके बाद आपके पति या पत्नी को वही पेंशन मिलती है, और उसके बाद जमा पैसा नॉमिनी को लौटाया जाता है।",
        "apply_apy": "आवेदन का तरीका। जिस बैंक या पोस्ट ऑफिस में बचत खाता है, वहाँ जाइए, या नेट बैंकिंग में अटल पेंशन योजना खोजिए। अपनी और नॉमिनी की जानकारी भरिए, खाते से पैसा अपने आप कटने की मंज़ूरी दीजिए, और फ़ॉर्म जमा कीजिए।",
        # health
        "health_ack": "ठीक है, इलाज। मैं आपसे एक छोटा सवाल पूछूँगी।",
        "q_health": "क्या आपका परिवार अनुसूचित जाति या जनजाति से है, या बिना ज़मीन के दिहाड़ी मज़दूरी से घर चलता है? हाँ के लिए 1, ना के लिए 2।",
        "health_likely": "आपका परिवार आयुष्मान भारत योजना के लिए पात्र हो सकता है। आखिरी फ़ैसला सरकारी सूची से होता है।",
        "health_list": "आयुष्मान भारत में पात्रता सरकारी सूची से तय होती है। आपका नाम सूची में है या नहीं, यह अस्पताल या जन सेवा केंद्र पर पता चल जाएगा।",
        "detail_pmjay": "आयुष्मान भारत, प्रधानमंत्री जन आरोग्य योजना। सरकारी वेबसाइट के अनुसार, हर परिवार को साल में पाँच लाख रुपये तक का इलाज सूचीबद्ध अस्पतालों में बिना नकद पैसे के मिलता है। दवाई, जाँच, ऑपरेशन और आईसीयू शामिल हैं, और पुरानी बीमारियाँ पहले दिन से कवर होती हैं।",
        "apply_pmjay": "कार्ड बनवाने का तरीका। नज़दीकी सूचीबद्ध अस्पताल या जन सेवा केंद्र जाइए। वहाँ आरोग्य मित्र आपके राशन कार्ड नंबर या मोबाइल नंबर से सूची में नाम खोजेंगे। आधार कार्ड दिखाइए, और आपके परिवार का ई-कार्ड बन जाएगा।",
        # jobs
        "jobs_menu": "ठीक है, रोज़गार। अपना काम या धंधा शुरू करना है, तो 1 दबाइए। काम सीखते हुए स्टाइपेंड वाली अप्रेंटिसशिप चाहिए, तो 2 दबाइए।",
        "conf_pmegp": "आपने अपना काम शुरू करना चुना। सही है तो 1 दबाइए, नहीं तो 2।",
        "conf_naps": "आपने अप्रेंटिसशिप चुनी। सही है तो 1 दबाइए, नहीं तो 2।",
        "detail_pmegp": "प्रधानमंत्री रोज़गार सृजन कार्यक्रम। सरकारी वेबसाइट के अनुसार, नया छोटा काम शुरू करने के लिए बैंक लोन पर सरकारी सब्सिडी मिलती है, नई यूनिट की लागत का पैंतीस प्रतिशत तक। अठारह साल से ऊपर कोई भी आवेदन कर सकता है, आय की कोई सीमा नहीं।",
        "apply_pmegp": "आवेदन का तरीका। पीएमईजीपी की सरकारी वेबसाइट पर जाइए। नई यूनिट के लिए अप्लाई पर क्लिक कीजिए, फ़ॉर्म भरिए, प्रोजेक्ट रिपोर्ट जैसे कागज़ अपलोड कीजिए, और जमा कीजिए।",
        "detail_naps": "राष्ट्रीय अप्रेंटिसशिप प्रोत्साहन योजना। सरकारी वेबसाइट के अनुसार, किसी कंपनी में काम सीखते हुए हर महीने नौ हज़ार रुपये तक का स्टाइपेंड मिलता है, जिसमें पंद्रह सौ रुपये तक सरकार सीधे बैंक खाते में देती है। सरकारी मदद के लिए रजिस्ट्रेशन के समय उम्र पैंतीस साल तक होनी चाहिए।",
        "apply_naps": "आवेदन का तरीका। अप्रेंटिसशिप इंडिया पोर्टल पर जाइए, कैंडिडेट के रूप में रजिस्टर कीजिए, मोबाइल ओटीपी और आधार ई-केवाईसी पूरा कीजिए, फिर अपने पास की ट्रेनिंग के लिए आवेदन कीजिए।",
        # common
        "q_apply": "क्या मैं आवेदन करने का तरीका बताऊँ? हाँ के लिए 1, ना के लिए 2।",
        "q_more": "क्या आप किसी और चीज़ के बारे में जानना चाहेंगे? हाँ के लिए 1, ना के लिए 2।",
        "bye": "हक़दार को कॉल करने के लिए धन्यवाद। आपका दिन शुभ हो। नमस्ते!",
    },
    "en": {
        "need_menu": "I will help you find government schemes. What do you need help with? For farming, press 1. For pension, press 2. For health, press 3. For jobs, press 4.",
        "conf_farm": "You chose farming. If that is right, press 1. If not, press 2.",
        "conf_pension": "You chose pension. If that is right, press 1. If not, press 2.",
        "conf_health": "You chose health. If that is right, press 1. If not, press 2.",
        "conf_jobs": "You chose jobs. If that is right, press 1. If not, press 2.",
        "conf_yes": "You said yes. If that is right, press 1. If not, press 2.",
        "conf_no": "You said no. If that is right, press 1. If not, press 2.",
        "not_understood": "Sorry, I did not understand. Please press a button.",
        "try_keys": "Okay. Please choose by pressing a button.",
        "wrong_key": "That button is not an option here.",
        "yn_keys": "Sorry. For yes press 1, for no press 2.",
        "sorry": "Sorry, I could not hear you. Once more.",
        "farm_ack": "Okay, schemes for farmers. To find the right ones, I will ask you two short questions.",
        "q_land": "First question. Is the farm land in your own name? For yes press 1, for no press 2.",
        "q_loan": "Second question. Do you need a loan for farming? For yes press 1, for no press 2.",
        "res_yy": "I found three schemes for you. One, PM Kisan Samman Nidhi, which gives six thousand rupees every year. Two, the Kisan Credit Card, a loan for farming. Three, Pradhan Mantri Fasal Bima Yojana, crop insurance at a low premium.",
        "res_yn": "I found two schemes for you. One, PM Kisan Samman Nidhi, which gives six thousand rupees every year. Two, Pradhan Mantri Fasal Bima Yojana, crop insurance at a low premium.",
        "res_ny": "Since the land is not in your name, PM Kisan does not apply. But two schemes are open to tenant farmers and sharecroppers too. One, the Kisan Credit Card, a loan for farming. Two, Pradhan Mantri Fasal Bima Yojana, crop insurance.",
        "res_nn": "Since the land is not in your name, PM Kisan does not apply. But Pradhan Mantri Fasal Bima Yojana, crop insurance, is open to tenant farmers and sharecroppers too.",
        "which_yy": "Which scheme would you like to know more about? For PM Kisan, press 1. For Kisan Credit Card, press 2. For crop insurance, press 3.",
        "which_yn": "Which scheme would you like to know more about? For PM Kisan, press 1. For crop insurance, press 2.",
        "which_ny": "Which scheme would you like to know more about? For Kisan Credit Card, press 1. For crop insurance, press 2.",
        "conf_pmkisan": "You chose PM Kisan. If that is right, press 1. If not, press 2.",
        "conf_kcc": "You chose Kisan Credit Card. If that is right, press 1. If not, press 2.",
        "conf_pmfby": "You chose crop insurance. If that is right, press 1. If not, press 2.",
        "detail_pmkisan": "PM Kisan Samman Nidhi. According to the official website, every eligible farmer family gets six thousand rupees a year, in three equal installments of two thousand rupees, every four months. You need an Aadhaar card, land papers, and a savings bank account.",
        "detail_kcc": "Kisan Credit Card. According to the official website, it gives a loan for growing crops, post-harvest expenses, and repairs of farm assets. Tenant farmers and sharecroppers can also apply. You need the application form, two photos, an ID proof like Aadhaar or voter card, and land papers.",
        "detail_pmfby": "Pradhan Mantri Fasal Bima Yojana. According to the official website, the farmer pays only two percent premium for Kharif crops, and one and a half percent for Rabi crops. The government pays the rest. It covers losses from drought, floods, pests, and diseases.",
        "apply_pmkisan": "How to apply. Visit the PM Kisan portal, or your nearest Common Service Centre. Choose New Farmer Registration, enter your Aadhaar and mobile number, enter the OTP, fill in the details, upload the documents, and submit.",
        "apply_kcc": "How to apply. Visit the website or branch of the bank you want the card from. Choose Kisan Credit Card, fill in the form, and submit. If you are eligible, the bank will contact you within three to four working days.",
        "apply_pmfby": "How to apply. Visit the Pradhan Mantri Fasal Bima Yojana website, or your nearest Common Service Centre. Fill in the registration form under Farmer Corner, with your land papers, bank passbook, and the crop you sowed. Apply within two weeks of the start of sowing.",
        "pension_ack": "Okay, pension. I will ask you two short questions.",
        "q_age": "First question. Are you between eighteen and forty years old? For yes press 1, for no press 2.",
        "q_account": "Second question. Do you have a savings account in a bank or post office? For yes press 1, for no press 2.",
        "pension_ok": "Good news. You can join the Atal Pension Yojana.",
        "pension_no_account": "Atal Pension Yojana needs a savings account in a bank or post office, because the monthly amount is paid from it. Please open an account first. Here is how the scheme works.",
        "pension_too_old": "Atal Pension Yojana can only be joined between eighteen and forty years of age. Right now my list has no other pension scheme for your age.",
        "detail_apy": "Atal Pension Yojana. According to the official website, after the age of sixty you get a guaranteed pension every month for life, from one thousand to five thousand rupees. After you, your spouse gets the same pension, and after that the saved money is returned to your nominee.",
        "apply_apy": "How to apply. Visit the bank or post office where you have your savings account, or search for Atal Pension Yojana in net banking. Fill in your and your nominee's details, allow the amount to be auto-debited from your account, and submit the form.",
        "health_ack": "Okay, health. I will ask you one short question.",
        "q_health": "Is your family from a Scheduled Caste or Scheduled Tribe, or a landless family that lives on daily wage labour? For yes press 1, for no press 2.",
        "health_likely": "Your family may be eligible for Ayushman Bharat. The final decision comes from the government list.",
        "health_list": "For Ayushman Bharat, eligibility comes from a government list. A hospital or Common Service Centre can check if your name is on it.",
        "detail_pmjay": "Ayushman Bharat, Pradhan Mantri Jan Arogya Yojana. According to the official website, every family gets cashless treatment up to five lakh rupees a year in empanelled hospitals. Medicines, tests, surgery, and ICU are covered, and old illnesses are covered from day one.",
        "apply_pmjay": "How to get the card. Visit an empanelled hospital or your nearest Common Service Centre. The Arogya Mitra there searches the list with your ration card or mobile number. Show your Aadhaar card, and your family's e-card is made.",
        "jobs_menu": "Okay, jobs. To start your own business, press 1. For an apprenticeship with a stipend while you learn, press 2.",
        "conf_pmegp": "You chose starting your own business. If that is right, press 1. If not, press 2.",
        "conf_naps": "You chose apprenticeship. If that is right, press 1. If not, press 2.",
        "detail_pmegp": "Prime Minister's Employment Generation Programme. According to the official website, to start a new small business you get a government subsidy on your bank loan, up to thirty five percent of the cost of a new unit. Anyone above eighteen can apply, with no income limit.",
        "apply_pmegp": "How to apply. Visit the official PMEGP website. Click Apply for a new unit, fill in the form, upload documents like the project report, and submit.",
        "detail_naps": "National Apprenticeship Promotion Scheme. According to the official website, while you learn a trade at a company you get a monthly stipend of up to nine thousand rupees, of which the government pays up to fifteen hundred rupees straight to your bank account. For government support you must be up to thirty five years old when you register.",
        "apply_naps": "How to apply. Visit the Apprenticeship India portal, register as a candidate, complete mobile OTP and Aadhaar e-KYC, then apply for a training place near you.",
        "q_apply": "Shall I tell you how to apply? For yes press 1, for no press 2.",
        "q_more": "Would you like to know about anything else? For yes press 1, for no press 2.",
        "bye": "Thank you for calling Haqdaar. Have a good day. Goodbye!",
    },
}

RESULTS = {  # (land in own name, needs loan) -> results line, scheme menu line, schemes in menu order
    (True, True): ("res_yy", "which_yy", ["pmkisan", "kcc", "pmfby"]),
    (True, False): ("res_yn", "which_yn", ["pmkisan", "pmfby"]),
    (False, True): ("res_ny", "which_ny", ["kcc", "pmfby"]),
    (False, False): ("res_nn", "", ["pmfby"]),
}

YES = {"हाँ", "हां", "हा", "जी", "हाँजी", "हम्म", "बिल्कुल", "ज़रूर", "जरूर", "ठीक", "सही", "yes", "yeah", "yep", "haan", "han", "ha", "sure", "okay", "ok", "right", "correct"}
NO = {"नहीं", "नही", "ना", "न", "मत", "गलत", "ग़लत", "no", "nahi", "nahin", "nope", "not", "wrong"}
# spoken words -> option (checked in order; "kisan" is in two scheme names)
WORDS: dict[str, tuple[str, ...]] = {
    "farm": ("खेती", "खेत", "केती", "केटी", "के दी", "किसान", "फसल", "फ़सल", "farm", "agri", "kisan", "kheti", "crop"),
    "pension": ("पेंशन", "पैंशन", "पेन्शन", "पेशन", "पेंसन", "पेशेंस", "बुढ़ापा", "pension", "patience", "retire"),
    "health": ("इलाज", "अस्पताल", "बीमारी", "सेहत", "स्वास्थ्य", "डॉक्टर", "health", "hospital", "doctor", "ilaj", "treatment"),
    "jobs": ("रोज़गार", "रोजगार", "नौकरी", "काम", "धंधा", "job", "work", "business", "rozgar", "naukri", "employment"),
    "kcc": ("क्रेडिट", "कार्ड", "लोन", "credit", "card", "loan"),
    "pmfby": ("बीमा", "फसल", "फ़सल", "bima", "insurance", "crop", "fasal"),
    "pmkisan": ("सम्मान", "निधि", "पीएम", "samman", "nidhi", "pm kisan", "किसान", "kisan"),
    "pmegp": ("अपना", "धंधा", "बिज़नेस", "बिजनेस", "business", "own", "start"),
    "naps": ("अप्रेंटिस", "स्टाइपेंड", "सीख", "ट्रेनिंग", "apprentice", "stipend", "training", "learn"),
}
HINTS = {  # expected words, given to Whisper so short answers are heard right
    "hi": {"need_menu": "खेती, पेंशन, इलाज, रोज़गार", "jobs_menu": "अपना काम, अप्रेंटिसशिप",
           "which": "किसान सम्मान निधि, किसान क्रेडिट कार्ड, फसल बीमा", "yn": "हाँ, नहीं"},
    "en": {"need_menu": "farming, pension, health, jobs", "jobs_menu": "own business, apprenticeship",
           "which": "PM Kisan, Kisan Credit Card, crop insurance", "yn": "yes, no"},
}


def say(line: str) -> None:
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {line}", flush=True)


# ---- voice out: Sarvam, prerendered -------------------------------------------
def _sarvam_key() -> str:
    return os.environ.get("SARVAM_API_KEY", "")


SARVAM_TTS_OK = [True]


def sarvam_tts(text: str, lang: str, online: bool = True) -> bytes:
    """Sarvam bulbul:v3 -> 8 kHz mu-law. Cached on disk."""
    key = hashlib.sha256(f"v3|{SPEAKER}|{lang}|{text}".encode()).hexdigest()[:24]
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{key}.ulaw"
    if out.exists():
        return out.read_bytes()
    if not online:
        raise FileNotFoundError(out)
    body = json.dumps({"inputs": [text], "target_language_code": TTS_LANG[lang], "speaker": SPEAKER,
                       "model": "bulbul:v3", "speech_sample_rate": 8000}).encode()
    req = urllib.request.Request("https://api.sarvam.ai/text-to-speech", data=body, headers={
        "api-subscription-key": _sarvam_key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        wav = base64.b64decode(json.loads(r.read())["audios"][0])
    with wave.open(io.BytesIO(wav)) as w:
        pcm, rate, width = w.readframes(w.getnframes()), w.getframerate(), w.getsampwidth()
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if rate != 8000:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, 8000, None)
    data = audioop.lin2ulaw(pcm, 2)
    tmp = CACHE / f"{key}.{threading.get_ident()}.part"
    tmp.write_bytes(data)
    tmp.replace(out)
    return data


AUDIO: dict[tuple[str, str], bytes] = {}
TEXT: dict[tuple[str, str], str] = {("hi", "greet"): GREET}
for _l, _lines in LINES.items():
    for _k, _t in _lines.items():
        TEXT[(_l, _k)] = _t
STATUS = {"ready": False, "lines": len(TEXT), "sarvam": 0, "mac_fallback": 0, "failed": 0}


def prerender() -> None:
    t0 = time.monotonic()

    def one(item: tuple[tuple[str, str], str]) -> None:
        (lang, name), text = item
        for attempt in range(2):
            try:
                AUDIO[(lang, name)] = sarvam_tts(text, lang, online=SARVAM_TTS_OK[0])
                STATUS["sarvam"] += 1
                return
            except FileNotFoundError:
                break
            except Exception as e:
                if "402" in str(e):
                    SARVAM_TTS_OK[0] = False
                    say("!! Sarvam has no credits: lines not already saved will use the Mac voice")
                    break
                if attempt == 1:
                    say(f"!! sarvam failed for {lang}/{name}: {e!r}; using Mac voice")
        try:
            AUDIO[(lang, name)] = mac_render(text, lang)
            STATUS["mac_fallback"] += 1
        except Exception as e:
            STATUS["failed"] += 1
            say(f"!! no voice for {lang}/{name}: {e!r}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(one, TEXT.items()))
    try:  # find out now, not mid-call, whether Sarvam can still hear (0.3 s of quiet)
        speech_to_text(b"\x00\x00" * 2400, "hi")
    except Exception as e:
        say(f"!! no speech-to-text works: {e!r}. Keys still work.")
    say(f"hearing: {'Sarvam' if SARVAM_STT_OK[0] else 'Groq Whisper'}")
    STATUS["ready"] = True
    if STATUS["mac_fallback"]:
        say(f"!! VOICE MIXED: {STATUS['mac_fallback']} lines in the Mac voice. Top up Sarvam credits and restart to fix.")
    say(f"voice ready: {STATUS['lines']} lines, sarvam {STATUS['sarvam']}, "
        f"mac fallback {STATUS['mac_fallback']}, failed {STATUS['failed']}, {time.monotonic() - t0:.1f} s")


# ---- ears: energy end-pointing + Sarvam speech-to-text -------------------------
START_RMS, END_RMS = 700, 400
START_FRAMES, END_FRAMES = 3, 40        # 20 ms frames: 60 ms to start, 800 ms of quiet to end
MAX_UTTERANCE_FRAMES = 350              # 7 s


def _multipart(fields: dict[str, str], wav: bytes) -> tuple[bytes, str]:
    b = "----haqdaar" + hashlib.md5(wav[-64:]).hexdigest()
    head = "".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items())
    head += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n'
    return head.encode() + wav + f"\r\n--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


SARVAM_STT_OK = [True]  # flips off after one failure (15 Sep: credits ran out) so Groq answers fast


def speech_to_text(pcm: bytes, lang: str, hint: str = "") -> tuple[str, str]:
    """Sarvam saarika first; Groq Whisper if Sarvam fails. lang: "" (unknown), "hi" or "en"."""
    quiet = b"\x00\x00" * 8000  # 1 s each side: Whisper garbles a lone short word without it (15 Sep)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(quiet + pcm + quiet)
    wav = buf.getvalue()
    if SARVAM_STT_OK[0] and _sarvam_key():
        body, ctype = _multipart({"model": "saarika:v2.5", "language_code": TTS_LANG.get(lang, "unknown")}, wav)
        req = urllib.request.Request("https://api.sarvam.ai/speech-to-text", data=body, headers={
            "api-subscription-key": _sarvam_key(), "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.loads(r.read())
            return j.get("transcript", ""), j.get("language_code", "")
        except Exception as e:
            SARVAM_STT_OK[0] = False
            say(f"!! sarvam speech-to-text failed ({e}); using Groq Whisper from now on")
    fields = {"model": "whisper-large-v3-turbo", "response_format": "verbose_json", "temperature": "0"}
    if lang:
        fields["language"] = lang
    if hint:
        fields["prompt"] = hint
    body, ctype = _multipart(fields, wav)
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=body, headers={
        "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}", "Content-Type": ctype,
        "User-Agent": "haqdaar/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read())
    code = {"hindi": "hi-IN", "english": "en-IN"}.get(str(j.get("language", "")).lower(), j.get("language", ""))
    return j.get("text", "").strip(), code


class Hangup(Exception):
    pass


class Heard:
    def __init__(self, text: str = "", lang: str = "", digit: str = "", spoke: bool = False):
        self.text, self.lang, self.digit, self.spoke = text, lang, digit, spoke

    @property
    def low(self) -> str:
        return f" {self.text.lower()} "


def yes_no_word(h: Heard) -> bool | None:
    """Key 1/2, or a clear yes/no word. None if unclear."""
    if h.digit in ("1", "2"):
        return h.digit == "1"
    words = set(re.split(r"[\s।,.?!]+", h.text.lower()))
    if words & NO:
        return False
    if words & YES:
        return True
    return None


def match_words(h: Heard, options: list[str]) -> str:
    for opt in options:
        if any(w in h.low for w in WORDS.get(opt, ())):
            return opt
    return ""


# ---- one call ------------------------------------------------------------------
class Call:
    def __init__(self, ws: WebSocket, sid: str, q: asyncio.Queue):
        self.ws, self.sid, self.q = ws, sid, q
        self.lang = "hi"
        self.lang_known = False
        self.marks = 0

    async def _event(self, timeout: float):
        ev = await asyncio.wait_for(self.q.get(), timeout)
        if isinstance(ev, StopEvent) or ev is None:
            raise Hangup()
        return ev

    async def speak(self, name: str, lang: str | None = None) -> str:
        """Play one line; returns a digit if the caller pressed a key while it played."""
        lang = lang or self.lang
        data = AUDIO[(lang, name)]
        say(f"BOT     [{lang}/{name}] {TEXT[(lang, name)][:90]}")
        for i in range(0, len(data), CHUNK):
            await self.ws.send_json(build_media(self.sid, data[i:i + CHUNK]))
        self.marks += 1
        mark = f"m{self.marks}_{name}"
        await self.ws.send_json(build_mark(self.sid, mark))
        deadline = time.monotonic() + len(data) / 8000 + 8
        while True:
            try:
                ev = await self._event(max(0.1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                say(f"!! no playback mark for {name}; moving on")
                return ""
            if isinstance(ev, MarkEvent) and ev.name == mark:
                return ""
            if isinstance(ev, DtmfEvent):
                say(f"CALLER  key {ev.digit} (while bot talked)")
                await self.ws.send_json(build_clear(self.sid))
                return ev.digit

    async def listen(self, hint: str = "") -> Heard:
        while not self.q.empty():  # drop audio queued while the line played (echo)
            ev = self.q.get_nowait()
            if isinstance(ev, StopEvent) or ev is None:
                raise Hangup()
            if isinstance(ev, DtmfEvent):
                say(f"CALLER  key {ev.digit}")
                return Heard(digit=ev.digit)
        voiced, quiet, started, frames, peak = 0, 0, False, [], 0
        pre: list[bytes] = []
        deadline = time.monotonic() + NO_SPEECH_WAIT
        while True:
            try:
                ev = await self._event(max(0.05, deadline - time.monotonic()) if not started else 2.0)
            except asyncio.TimeoutError:
                if not started:
                    say(f"CALLER  (silence, peak level {peak})")
                    return Heard()
                break
            if isinstance(ev, DtmfEvent):
                say(f"CALLER  key {ev.digit}")
                return Heard(digit=ev.digit)
            if not isinstance(ev, MediaEvent):
                continue
            pcm = audioop.ulaw2lin(ev.payload_bytes, 2)
            level = audioop.rms(pcm, 2)
            peak = max(peak, level)
            if not started:
                pre = (pre + [pcm])[-15:]
                voiced = voiced + 1 if level > START_RMS else 0
                if voiced >= START_FRAMES:
                    started, frames = True, list(pre)
                elif time.monotonic() > deadline:
                    say(f"CALLER  (silence, peak level {peak})")
                    return Heard()
                continue
            frames.append(pcm)
            quiet = quiet + 1 if level < END_RMS else 0
            if quiet >= END_FRAMES or len(frames) >= MAX_UTTERANCE_FRAMES:
                break
        t0 = time.monotonic()
        try:
            text, lang = await asyncio.wait_for(asyncio.to_thread(
                speech_to_text, b"".join(frames), self.lang if self.lang_known else "", hint), STT_WAIT)
            say(f"CALLER  said: \"{text}\" ({lang}, {len(frames) * 20} ms audio, stt {time.monotonic() - t0:.1f} s)")
        except Exception as e:
            text, lang = "", ""
            say(f"CALLER  spoke {len(frames) * 20} ms; stt gave nothing in time ({type(e).__name__})")
        return Heard(text, lang, spoke=True)

    async def ask(self, name: str, hint: str = "") -> Heard:
        digit = await self.speak(name)
        return Heard(digit=digit) if digit else await self.listen(hint)

    async def confirm(self, line: str) -> bool:
        """Read back what speech gave us: 1 = right, 2 = wrong. Silence twice = right."""
        for _ in range(2):
            ok = yes_no_word(await self.ask(line, HINTS[self.lang]["yn"]))
            if ok is not None:
                say(f"--      confirm {line}: {'right' if ok else 'WRONG'}")
                return ok
        return True

    async def choose(self, menu: str, options: list[str], hint_key: str = "", default: bool = True) -> str:
        """Button menu. Speech also works, but is always confirmed with 1/2.
        default=False: never pick for the caller (returns "" after 3 failed tries)."""
        hint = HINTS[self.lang].get(hint_key or menu, "")
        for _ in range(3):
            h = await self.ask(menu, hint)
            if h.digit:
                if h.digit.isdigit() and 1 <= int(h.digit) <= len(options):
                    return options[int(h.digit) - 1]
                await self.speak("wrong_key")
                continue
            if h.spoke:
                opt = match_words(h, options)
                if not opt:
                    await self.speak("not_understood")
                    continue
                if await self.confirm(f"conf_{opt}"):
                    return opt
                await self.speak("try_keys")
                continue
            await self.speak("sorry")
        if not default:
            say(f"--      {menu}: no answer after 3 tries")
            return ""
        say(f"--      {menu}: no answer, taking {options[0]}")
        return options[0]

    async def yesno(self, question: str, default: bool = True) -> bool:
        for _ in range(2):
            h = await self.ask(question, HINTS[self.lang]["yn"])
            if h.digit in ("1", "2"):
                return h.digit == "1"
            if h.spoke:
                ans = yes_no_word(h)
                if ans is not None:
                    return ans if await self.confirm("conf_yes" if ans else "conf_no") else not ans
                await self.speak("yn_keys")
                continue
            await self.speak("sorry")
        return default

    async def scheme(self, s: str) -> None:
        say(f"--      scheme: {s}")
        await self.speak(f"detail_{s}")
        if await self.yesno("q_apply"):
            await self.speak(f"apply_{s}")

    async def path_farm(self) -> None:
        await self.speak("farm_ack")
        land = await self.yesno("q_land")
        loan = await self.yesno("q_loan")
        say(f"--      land in own name: {land}, needs loan: {loan}")
        result, menu, offered = RESULTS[(land, loan)]
        await self.speak(result)
        await self.scheme(offered[0] if not menu else await self.choose(menu, offered, "which"))

    async def path_pension(self) -> None:
        await self.speak("pension_ack")
        if not await self.yesno("q_age"):
            await self.speak("pension_too_old")
            return
        await self.speak("pension_ok" if await self.yesno("q_account") else "pension_no_account")
        await self.scheme("apy")

    async def path_health(self) -> None:
        await self.speak("health_ack")
        await self.speak("health_likely" if await self.yesno("q_health") else "health_list")
        await self.scheme("pmjay")

    async def path_jobs(self) -> None:
        await self.scheme(await self.choose("jobs_menu", ["pmegp", "naps"]))

    async def run(self) -> None:
        h = await self.ask_greet()
        t = h.low
        if h.digit == "2" or (not h.digit and ("english" in t or "इंग्लिश" in t or "अंग्रेज" in t
                                               or (h.lang == "en-IN" and "hindi" not in t and "हिंदी" not in t))):
            self.lang = "en"
        self.lang_known = True
        say(f"--      language: {self.lang}")
        for _ in range(4):
            need = await self.choose("need_menu", ["farm", "pension", "health", "jobs"], default=False)
            say(f"--      need: {need or 'none, ending call'}")
            if not need:
                break
            await getattr(self, f"path_{need}")()
            if not await self.yesno("q_more", default=False):
                break
        await self.speak("bye")

    async def ask_greet(self) -> Heard:
        for _ in range(2):
            h = await self.ask_raw_greet()
            if h.digit or h.spoke:
                return h
        return Heard()

    async def ask_raw_greet(self) -> Heard:
        digit = await self.speak("greet", "hi")
        return Heard(digit=digit) if digit else await self.listen("Hindi, English, हिंदी")


# ---- server --------------------------------------------------------------------
app = FastAPI(title="haqdaar-voice-demo")


@app.on_event("startup")
def _warm() -> None:
    threading.Thread(target=prerender, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    return STATUS


@app.api_route("/answer", methods=["GET", "POST"])
def answer() -> Response:
    domain = os.environ.get("NGROK_DOMAIN", "")
    say("answer  line picked up, sent voice demo stream XML")
    return Response(content=build_stream_twiml(f"wss://{domain}/voice", keep_call_alive=False),
                    media_type="text/xml")


@app.websocket("/voice")
async def voice(ws: WebSocket) -> None:
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    task: asyncio.Task | None = None

    async def run_call(sid: str) -> None:
        call = Call(ws, sid, q)
        try:
            if not STATUS["ready"]:
                say("!! call came before voice was ready; waiting")
                while not STATUS["ready"]:
                    await asyncio.sleep(0.2)
            await call.run()
            say("call    finished, hanging up")
        except Hangup:
            say("call    caller hung up")
        except Exception as e:
            say(f"!! call error: {e!r}")
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    try:
        while True:
            ev = parse_event(await ws.receive_text())
            if isinstance(ev, StartEvent):
                say(f"start   stream={ev.stream_sid}")
                task = asyncio.create_task(run_call(ev.stream_sid))
            elif isinstance(ev, (MediaEvent, DtmfEvent, MarkEvent, StopEvent)):
                q.put_nowait(ev)
                if isinstance(ev, StopEvent):
                    break
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        say(f"socket  {e!r}")
    finally:
        q.put_nowait(None)
        if task:
            await asyncio.gather(task, return_exceptions=True)
        say("socket  closed")
