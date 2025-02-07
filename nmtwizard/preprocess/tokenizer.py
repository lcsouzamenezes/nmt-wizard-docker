"""Tokenization utilities."""

import pyonmttok

_ALLOWED_TOKENIZER_ARGS = set(
    [
        "bpe_dropout",
        "bpe_model_path",
        "case_feature",
        "case_markup",
        "joiner",
        "joiner_annotate",
        "joiner_new",
        "lang",
        "mode",
        "no_substitution",
        "preserve_placeholders",
        "preserve_segmented_tokens",
        "segment_alphabet",
        "segment_alphabet_change",
        "segment_case",
        "segment_numbers",
        "soft_case_regions",
        "sp_alpha",
        "sp_model_path",
        "sp_nbest_size",
        "spacer_annotate",
        "spacer_new",
        "support_prior_joiners",
        "vocabulary_path",
        "vocabulary_threshold",
    ]
)


def _is_valid_language_code(lang):
    # TODO: consider exposing this function in pyonmttok.
    return len(lang) == 2 and lang not in ("xx", "yy")


def build_tokenizer(args):
    """Builds a tokenizer based on user arguments."""
    args = {
        name: value for name, value in args.items() if name in _ALLOWED_TOKENIZER_ARGS
    }
    if not args:
        return None
    lang = args.get("lang")
    if lang is not None and not _is_valid_language_code(lang):
        args.pop("lang")
    return pyonmttok.Tokenizer(**args)


def make_subword_learner(subword_config, subword_dir, tokenizer=None):
    params = subword_config.get("params")
    if params is None:
        raise ValueError(
            "'params' field should be specified for subword model learning."
        )
    subword_type = subword_config.get("type")
    if subword_type is None:
        raise ValueError("'type' field should be specified for subword model learning.")
    vocab_size = params.get("vocab_size")
    if vocab_size is None:
        raise ValueError(
            "'vocab_size' parameter should be specified for subword model learning."
        )

    if subword_type == "bpe":
        learner = pyonmttok.BPELearner(
            tokenizer=tokenizer,
            symbols=vocab_size,
            min_frequency=params.get("min-frequency", 0),
            total_symbols=params.get("total_symbols", False),
        )
    elif subword_type == "sp":
        learner = pyonmttok.SentencePieceLearner(tokenizer=tokenizer, **params)
    else:
        raise ValueError("Invalid subword type : '%s'." % subword_type)

    return {"learner": learner, "subword_type": subword_type, "size": vocab_size}


def vocabulary_iterator(vocabulary_path):
    """Iterates over each token included in the vocabulary file."""
    with open(vocabulary_path) as vocabulary_file:
        header = True
        for line in vocabulary_file:
            # The vocabulary file might start with some comments prefixed with '#'.
            if header and line[0] == "#":
                continue
            header = False
            line = line.rstrip("\n\r")
            fields = line.split(" ")
            if len(fields) == 1:
                # No frequency value, the line is just the token.
                yield fields[0]
            else:
                # The code below checks the last field is a frequency and not a part of
                # a badly formatted token.
                try:
                    float(fields[-1])
                    fields.pop()
                except ValueError:
                    pass
                yield " ".join(fields)


def load_vocabulary(vocabulary_path):
    if vocabulary_path and isinstance(vocabulary_path, str):
        return set(vocabulary_iterator(vocabulary_path))
    return vocabulary_path
