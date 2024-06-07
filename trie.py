class Node:
    def __init__(self):
        """
        This method initializes a node in the trie.
        It sets 'end' attribute to False, signifying that the current node is not the end of a word.
        It also sets 'children' as an empty dictionary to hold child nodes.
        """
        self.end = False
        self.children = {}

    def autocomplete(self, prefix):
        """
        This method autocompletes the words recursively in the Trie.
        It generates all the possible words that start with the given prefix.

        :param prefix: The prefix input to the function
        :return: Yields the autocompleted words
        """
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
        """
        This method initializes the Trie (the root of it to be specific).
        It sets 'root' as a new Node.
        """
        self.root = Node()

    def insert(self, word):
        """
        This method inserts a word into the Trie.
        It iteratively creates nodes for each character in the word and
        sets the 'end' attribute of the final character's node as True.

        :param word: The word to be inserted into the Trie
        """
        cur = self.root
        for c in word.lower():
            if c not in cur.children:
                cur.children[c] = Node()
            cur = cur.children[c]
        cur.end = True

    def autocomplete(self, word):
        """
        This method finds all words in the Trie that start with a given word/prefix.

        :param word: The word/prefix used to autocomplete
        :return: Yields all possible words in Trie starting with the given word
        """
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
