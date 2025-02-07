import random
import pyonmttok
import os
import copy
import unicodedata

from nmtwizard.preprocess import prepoperator
from nmtwizard.preprocess.tu import TokReplace
import fasttext


@prepoperator.register_operator("noise")
class Noise(prepoperator.TUOperator):
    @classmethod
    def _config_schema(cls):
        schema = super(Noise, cls)._config_schema()

        noise_block = {
            "lang": {"type": "string"},
            "data_augmentation": {"type": "boolean"},
            "drop_word_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "duplicate_word_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "swap_word_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "substitute_word": {
                "properties": {
                    "prob": {"type": "number", "minimum": 0, "maximum": 1},
                    "word_embedding_file": {"type": "string"},
                    "nearest_neighbors_num": {"type": "integer"},
                },
                "type": "object",
                "additionalProperties": False,
            },
            "drop_space_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "insert_space_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "drop_char_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "duplicate_char_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "swap_char_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "substitute_char_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "add_marker": {"type": "boolean"},
            "char_equivalence_prob": {"type": "number", "minimum": 0, "maximum": 1},
            "char_equivalence_table": {"type": "object"},
        }
        schema["properties"].update(
            {
                "source": {
                    "type": "object",
                    "properties": noise_block,
                    "additionalProperties": False,
                }
            }
        )
        schema["properties"].update(noise_block)

        return schema

    @staticmethod
    def is_applied_for(process_type):
        return process_type.training

    def __init__(self, config, *args):
        source_config = config.get("source")
        if source_config:
            config = source_config
        self._data_augmentation = config.get("data_augmentation", False)
        self._drop_word_prob = config.get("drop_word_prob", 0)
        self._duplicate_word_prob = config.get("duplicate_word_prob", 0)
        self._swap_word_prob = config.get("swap_word_prob", 0)
        substitute_word_config = config.get("substitute_word", None)
        self._substitute_word_prob = 0
        if substitute_word_config:
            self._substitute_word_prob = substitute_word_config.get("prob", 0)
            if self._substitute_word_prob:
                # TODO: SharedState builder ?
                word_embedding_file = substitute_word_config.get("word_embedding_file")
                self._word_embedding_model = None
                if word_embedding_file is not None:
                    if not os.path.isfile(word_embedding_file):
                        raise ValueError(
                            "Word embedding file doesn't exist: %s"
                            % (word_embedding_file)
                        )
                    self._word_embedding_model = fasttext.load_model(
                        word_embedding_file
                    )
                    self._nn = substitute_word_config.get("nearest_neighbors_num")
        self._drop_space_prob = config.get("drop_space_prob", 0)
        self._insert_space_prob = config.get("insert_space_prob", 0)
        self._drop_char_prob = config.get("drop_char_prob", 0)
        self._duplicate_char_prob = config.get("duplicate_char_prob", 0)
        self._swap_char_prob = config.get("swap_char_prob", 0)
        self._substitute_char_prob = config.get("substitute_char_prob", 0)
        self._char_equivalence_prob = config.get("char_equivalence_prob", 0)
        self._char_equivalence_table = config.get("char_equivalence_table", {})
        self._add_marker = config.get("add_marker", 0)

    def _preprocess_tu(self, tu, *args):
        original_tokens = (
            [pyonmttok.Token(token) for token in tu.src_tok.token_objects[0]]
            if self._add_marker or self._data_augmentation
            else None
        )
        if self._insert_space_prob > 0:
            tu = self._apply_space_insertion_noise(tu)
        src_tok = tu.src_tok
        tokens = src_tok.token_objects[0]
        new_tokens = self._apply_word_noise(tokens)
        result = [tu]
        tu.src_tok = (src_tok.tokenizer, [new_tokens])
        if original_tokens is not None and new_tokens != original_tokens:
            if self._data_augmentation:
                original_tu = copy.deepcopy(tu)
                original_tu.src_tok = (src_tok.tokenizer, [original_tokens])
                result.append(original_tu)
            if self._add_marker:
                tu.replace_tokens_side("source", (0, 0, ["｟mrk_noisy｠"]))
        return result

    def _apply_space_insertion_noise(self, tu):
        src_tok = tu.src_tok
        tokens = src_tok.token_objects[0]
        added_spaces = 0
        for pos, token in enumerate(tokens):
            if not token.is_placeholder():
                if (
                    self._insert_space_prob > 0
                    and random.random() <= self._insert_space_prob
                    and len(token) > 1
                ):
                    new_space_index = random.randint(1, len(token) - 1)
                    first_part_surface = token.surface[0:new_space_index]
                    second_part_surface = token.surface[new_space_index:]
                    tu.replace_tokens_side(
                        "source",
                        (
                            pos + added_spaces,
                            1,
                            [first_part_surface, second_part_surface],
                        ),
                    )
                    added_spaces += 1
        return tu

    def _apply_word_noise(self, tokens):
        new_tokens = []
        for token in tokens:
            if not token.is_placeholder():
                if self._drop_word_prob > 0 and random.random() <= self._drop_word_prob:
                    continue
                elif (
                    self._duplicate_word_prob > 0
                    and random.random() <= self._duplicate_word_prob
                ):
                    new_tokens.extend([token, token])
                    continue
                elif (
                    len(new_tokens) > 0
                    and self._swap_word_prob > 0
                    and random.random() <= self._swap_word_prob
                ):
                    new_tokens.insert(-1, token)
                    continue
                elif (
                    self._substitute_word_prob > 0
                    and self._word_embedding_model is not None
                    and random.random() <= self._substitute_word_prob
                    and all(c.isalpha() for c in token.surface)
                ):
                    nearest_neighbors = (
                        self._word_embedding_model.get_nearest_neighbors(
                            token.surface, k=self._nn
                        )
                    )
                    nearest_neighbors = [
                        nn[1]
                        for nn in nearest_neighbors
                        if all(c.isalpha() for c in nn[1])
                    ]
                    if nearest_neighbors:
                        token.surface = random.choice(nearest_neighbors)
                    new_tokens.append(token)
                    continue
                elif (
                    self._drop_space_prob > 0
                    and random.random() <= self._drop_space_prob
                ):
                    token.join_left = True

                if (
                    self._drop_char_prob > 0
                    or self._duplicate_char_prob > 0
                    or self._swap_char_prob > 0
                    or self._substitute_char_prob > 0
                ):
                    token.surface = self._apply_character_noise(token.surface)

                if (
                    self._char_equivalence_prob > 0
                    and self._char_equivalence_table
                    and random.random() <= self._char_equivalence_prob
                ):
                    token.surface = self._apply_char_equivalence_noise(token.surface)

            if len(token.surface) != 0:  # Delete token if empty.
                new_tokens.append(token)
        return new_tokens

    @staticmethod
    def get_neighbor_keys_on_qwerty(original_key):
        if original_key.isupper():
            key = original_key.lower()
        else:
            key = original_key
        lines = "qwertyuiop", "asdfghjkl", "zxcvbnm"
        index_list = [(i, l.find(key)) for i, l in enumerate(lines) if key in l]
        if index_list:
            line_index, index = index_list[0]
        else:
            return []
        lines = lines[line_index - 1 : line_index + 2] if line_index else lines[0:2]
        result = [
            line[index + i]
            for line in lines
            for i in [-1, 0, 1]
            if len(line) > index + i and line[index + i] != key and index + i >= 0
        ]
        if original_key.isupper():
            return [r.upper() for r in result]
        else:
            return result

    def _apply_character_noise(self, cur_surface):
        new_surface = ""
        i = 0
        while i < len(cur_surface):
            if self._drop_char_prob > 0 and random.random() <= self._drop_char_prob:
                pass
            elif (
                self._duplicate_char_prob > 0
                and random.random() <= self._duplicate_char_prob
            ):
                new_surface += cur_surface[i] * 2
            elif (
                self._swap_char_prob > 0
                and i + 1 < len(cur_surface)
                and random.random() <= self._swap_char_prob
            ):
                new_surface += cur_surface[i + 1]
                new_surface += cur_surface[i]
                i += 1
            elif (
                self._substitute_char_prob > 0
                and random.random() <= self._substitute_char_prob
                and cur_surface[i].isalpha()
            ):
                key = cur_surface[i]
                neighbors = self.get_neighbor_keys_on_qwerty(key)
                new_surface += random.choice(neighbors) if neighbors else key
            else:
                new_surface += cur_surface[i]
            i += 1
        return new_surface

    def _apply_char_equivalence_noise(self, cur_surface):
        new_surface = unicodedata.normalize("NFD", cur_surface)
        for k, v in self._char_equivalence_table.items():
            new_surface = new_surface.replace(k, v)
        new_surface = unicodedata.normalize("NFC", new_surface)
        return new_surface
