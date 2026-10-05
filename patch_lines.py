with open("haqdaar/audio/lines.yaml", "r") as f:
    lines = f.read()
lines = lines.replace("""  opener_prompt:
    pinned: true
    en: "Tell me what you need help with. You can also say the name of a scheme."
    hi: "बताइए, आपको किस बात में मदद चाहिए। आप किसी योजना का नाम भी बता सकते हैं।"
    mr: "तुम्हाला कशात मदत हवी आहे ते सांगा. तुम्ही योजनेचे नाव देखील सांगू शकता." """, """  opener_prompt:
    pinned: true
    en: "Tell me what you need help with. You can also say the name of a scheme."
    hi: "बताइए, आपको किस बात में मदद चाहिए। आप किसी योजना का नाम भी बता सकते हैं।"
    mr: "तुम्हाला कशात मदत हवी आहे ते सांगा. तुम्ही योजनेचे नाव देखील सांगू शकता."

  opener_short_prompt:
    en: "What do you want to know? Say it, or press 0 for the list."
    hi: "आप क्या जानना चाहते हैं? बोलें, या सूची के लिए 0 दबाएं।"
    mr: "तुम्हाला काय जाणून घ्यायचे आहे? सांगा, किंवा सूचीसाठी 0 दाबा."

  did_not_get_reply:
    en: "I did not get your reply. Here is the menu again:"
    hi: "मुझे आपका जवाब नहीं मिला। यहाँ मेनू फिर से है:"
    mr: "मला तुमचे उत्तर मिळाले नाही. येथे मेनू पुन्हा आहे:" """)

with open("haqdaar/audio/lines.yaml", "w") as f:
    f.write(lines)
