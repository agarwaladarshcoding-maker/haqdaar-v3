with open('haqdaar/audio/lines.yaml', 'r') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if line.startswith('  unclear_prompt:'):
        new_lines.insert(-1, '  opener_short_prompt:\n    en: "What do you want to know? Say it, or press 0 for the list."\n    hi: "आप क्या जानना चाहते हैं? बोलें, या सूची के लिए 0 दबाएं।"\n    mr: "तुम्हाला काय जाणून घ्यायचे आहे? सांगा, किंवा सूचीसाठी 0 दाबा."\n\n  did_not_get_reply:\n    en: "I did not get your reply. Here is the menu again:"\n    hi: "मुझे आपका जवाब नहीं मिला। यहाँ मेनू फिर से है:"\n    mr: "मला तुमचे उत्तर मिळाले नाही. येथे मेनू पुन्हा आहे:"\n\n')

with open('haqdaar/audio/lines.yaml', 'w') as f:
    f.writelines(new_lines)
