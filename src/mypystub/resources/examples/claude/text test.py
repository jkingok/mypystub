# String handling and dictionaries, standard library only.
text = "the quick brown fox jumps over the lazy dog the end"
counts = {}
for word in text.split():
    counts[word] = counts.get(word, 0) + 1

for word in sorted(counts):
    print(word, counts[word])

print("Unique words:", len(counts))
