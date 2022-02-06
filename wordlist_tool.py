#!/usr/bin/env python3

import argparse
import hunspell  # type: ignore
import math
import time
import unicodedata

from nltk.tokenize import wordpunct_tokenize  # type: ignore
from nltk.util import ngrams  # type: ignore
from pathlib import Path

from typing import Optional

HUNSPELL_DICT_PATH = "/usr/share/hunspell/"
MONOGRAM_SPACE = 175


Monogram = tuple[tuple[str], int]
Bigram = tuple[tuple[str, str], int]


def dict_normalize(word: str) -> str:
    return unicodedata.normalize("NFC", word).lower()


def word_cnt_to_freq(word_cnt: int, max_cnt: int, bigram: bool = False) -> int:
    # Integer between 0 and 255 on a logarithmic scale of 1.15, but 0 means profanity
    # Split freq space to better handle bigrams
    if bigram:
        return round((255 - MONOGRAM_SPACE - 1) * (math.log(word_cnt, 1.15) / math.log(max_cnt, 1.15))
                     + MONOGRAM_SPACE + 1)
    return round((MONOGRAM_SPACE - 1) * (math.log(word_cnt, 1.15) / math.log(max_cnt, 1.15)) + 1)


def generate_ngrams(input_file_path: str, profanity: Optional[set[str]] = None) -> tuple[list[Monogram], list[Bigram]]:
    if not profanity:
        profanity = set()
    monograms: dict[tuple[str], int] = {}
    bigrams: dict[tuple[str, str], int] = {}
    with open(input_file_path, "r") as input_file:
        for line in input_file:
            tokenized = wordpunct_tokenize(line)
            for monogram in [(dict_normalize(i[0]),) for i in ngrams(tokenized, 1)]:
                if all([i.isalpha() for i in monogram]):
                    if monogram not in monograms:
                        monograms[monogram] = 0
                    if all([i not in profanity for i in monogram]):
                        monograms[monogram] += 1

            for bigram in [(dict_normalize(i[0]), dict_normalize(i[1]),) for i in ngrams(tokenized, 2)]:
                if all([i.isalpha() for i in bigram]) and all([i not in profanity for i in bigram]):
                    if bigram not in bigrams:
                        bigrams[bigram] = 0
                    bigrams[bigram] += 1
    monogram_list = sorted(monograms.items(), key=lambda i: i[1], reverse=True)
    bigram_list = sorted(bigrams.items(), key=lambda i: i[1], reverse=True)

    return monogram_list, bigram_list


def write_wordlist(monograms: list[Monogram], bigrams: list[Bigram], lang: str, description: str,
                   output_file_path: str, offensive: Optional[set[str]] = None) -> None:
    if not offensive:
        offensive = set()
    lang_code = lang
    if "_" not in lang_code:
        lang_code = "{language}_{region}".format(language=lang.lower(), region=lang.upper())

    hobj = hunspell.HunSpell(Path(HUNSPELL_DICT_PATH, "{lang_code}.dic".format(lang_code=lang_code)),
                             Path(HUNSPELL_DICT_PATH, "{lang_code}.aff".format(lang_code=lang_code)))

    header = "dictionary=main:{},locale={},description={},date={},version=1".format(lang.lower(), lang, description,
                                                                                    int(time.time()))

    max_monogram_cnt = max([i[1] for i in monograms])
    max_bigram_cnt = max([i[1] for i in bigrams])

    bigram_dict: dict[str, list[tuple[str, int]]] = {}
    for bigram in bigrams:
        if bigram[0][0] not in bigram_dict:
            bigram_dict[bigram[0][0]] = []
        bigram_dict[bigram[0][0]].append((bigram[0][1], bigram[1],))

    with open(output_file_path, "w") as output_file:
        output_file.write(header + "\n")
        for monogram in monograms:
            word: Optional[str] = None
            try:
                if hobj.spell(monogram[0][0]):
                    word = monogram[0][0]
                elif hobj.spell(monogram[0][0].capitalize()):
                    word = monogram[0][0].capitalize()
            except UnicodeEncodeError:
                pass
            if word:
                if monogram[1] == 0:
                    freq = 0
                else:
                    freq = word_cnt_to_freq(monogram[1], max_monogram_cnt)
                word_entry = "word={word},f={freq}".format(word=word, freq=freq)
                if word in offensive:
                    word_entry += ",possibly_offensive=true"
                output_file.write(" " + word_entry + "\n")
                for bigram_complement in bigram_dict.get(word, []):
                    bigram_complement_word = bigram_complement[0]
                    try:
                        if hobj.spell(bigram_complement_word):
                            bigram_complement_freq = word_cnt_to_freq(bigram_complement[1], max_bigram_cnt, bigram=True)
                            bigram_entry = "bigram={word},f={freq}"\
                                .format(word=bigram_complement_word, freq=bigram_complement_freq)
                            if bigram_complement_word in offensive:
                                bigram_entry += ",possibly_offensive=true"
                            output_file.write("  " + bigram_entry + "\n")
                    except UnicodeEncodeError:
                        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate AOSP keyboard wordlist form language dump file.")
    parser.add_argument("-l", "--lang", required=True, type=str, help="Language code")
    parser.add_argument("-i", "--input", required=True, type=str, help="Path to language dump file")
    parser.add_argument("-o", "--output", required=True, type=str, help="Path to output file")
    parser.add_argument("--profanity", type=str, help="Path to file of words to mark as profanity")
    parser.add_argument("--offensive", type=str, help="Path to file of words to mark as potentially offensive")
    parser.add_argument("-n", "--limit", default=10**7, type=int,
                        help="Maximum number of monograms and bigrams to write")
    parser.add_argument("-m", "--description", required=True, type=str, help="Language code")
    args = parser.parse_args()

    m_profanity: list[str] = []
    if args.profanity:
        with open(args.profanity, "r") as profanity_file:
            for m_line in profanity_file:
                m_profanity.append(m_line.strip())

    m_monograms, m_bigrams = generate_ngrams(args.input, profanity=set(m_profanity))

    monogram_limit = args.limit
    bigram_limit = min(5 * 10**4, args.limit)

    m_offensive: list[str] = []
    if args.offensive:
        with open(args.offensive, "r") as offensive_file:
            for m_line in offensive_file:
                m_offensive.append(m_line.strip())

    write_wordlist(m_monograms[:args.limit], m_bigrams[:bigram_limit], args.lang, args.description, args.output,
                   offensive=set(m_offensive + m_profanity))
