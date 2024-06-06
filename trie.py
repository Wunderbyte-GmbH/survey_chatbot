class Node:
    def __init__(self):
        self.end = False
        self.children = {}

    def autocomplete(self, prefix):
        # we're at the end of a word, yield the result
        if self.end:
            yield prefix

        # else, recurse over each child-character
        # of the current node and append the
        # corresponding letter to the prefix
        # -> this will build up the autocompleted string
        for letter, child in self.children.items():
            yield from child.autocomplete(prefix + letter)


class Trie:
    def __init__(self):
        self.root = Node()

    def insert(self, word):
        cur = self.root
        for c in word.lower():
            if c not in cur.children:
                cur.children[c] = Node()
            cur = cur.children[c]
        cur.end = True

    def autocomplete(self, word):
        cur = self.root
        # starting at the root
        # traverse the trie for each
        # character in `word`
        for c in word:
            cur = cur.children.get(c)
            if cur is None:  # word does not exist in our trie
                return

        # recursively autocomplete all possible words
        # starting at the final character node
        yield from cur.autocomplete(word)
