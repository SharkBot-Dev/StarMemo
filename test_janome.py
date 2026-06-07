from janome.tokenizer import Tokenizer

tokenizer = Tokenizer()

def extract_keywords(text):
    tokens = tokenizer.tokenize(text)
    keywords = set()
    for token in tokens:
        part_of_speech = token.part_of_speech.split(',')[0]
        if part_of_speech in ['名詞', '動詞', '形容詞']:
            keywords.add(token.base_form)
    return keywords

memos = [
    "今日はいい天気ですね",
    "明日の天気はどうかな",
    "美味しいラーメンを食べたい",
    "昨日はラーメンを食べた",
    "プログラミングは楽しい"
]

memos_with_keywords = []
for text in memos:
    keywords = extract_keywords(text)
    memos_with_keywords.append({"text": text, "keywords": keywords})
    print(f"Text: {text}")
    print(f"Keywords: {keywords}")

print("\nConnections:")
for i in range(len(memos_with_keywords)):
    for j in range(i + 1, len(memos_with_keywords)):
        k1 = memos_with_keywords[i]['keywords']
        k2 = memos_with_keywords[j]['keywords']
        intersection = k1.intersection(k2)
        if intersection:
            print(f"Connected: '{memos[i]}' <-> '{memos[j]}' (via {intersection})")
