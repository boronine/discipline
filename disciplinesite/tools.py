# -*- coding: utf-8 -*-

import random

vowels = "aeiou"
consonants = 'bcdfghjklmnpqrstvwz'

def _vowel():
    return random.choice(vowels)
 
def _consonant():
    return random.choice(consonants)
 
def _cv():
    return _consonant() + _vowel()
 
def _cvc():
    return _cv() + _consonant()
 
def _syllable():
    return random.choice([_vowel, _cv, _cvc])()
 
def word(cap=False):
    """ This function generates a fake word by creating between two and three
        random syllables and then joining them together.
    """
    syllables = []
    for x in range(random.randint(2,3)):
        syllables.append(_syllable())
    word = "".join(syllables)
    if cap: word = word[0].upper() + word[1:]
    return word
   
def sentence():
    ret = word(True)
    for i in range(random.randint(5,15)):
        ret += " " + word()
        if random.randint(0,5) == 0:
             ret += ","
    return ret + ". "

def mutate(word):
    p = random.randint(0,len(word)-1)
    w = word[:p]
    if word[p] in vowels: w += _vowel()
    else: w += _consonant()
    newword = w + word[p+1:]
    if newword == word: return mutate(word)
    return  w + word[p+1:]

