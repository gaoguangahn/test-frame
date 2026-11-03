import re


class WatcherRuleItem:
    def __init__(self, data: dict):
        self.text = data.get("text")
        self.description = data.get("description")
        self.text_regex = data.get("text_regex")
        self.description_regex = data.get("description_regex")
        self.action = data.get("action") or {"type": "click"}

        self.compiled_text_regex = (
            re.compile(self.text_regex) if self.text_regex else None
        )
        self.compiled_description_regex = (
            re.compile(self.description_regex) if self.description_regex else None
        )

    def name(self):
        return (
            self.text or self.text_regex or self.description or self.description_regex
        )

    def match_text(self, value: str) -> bool:
        if not value:
            return False
        if self.text is not None:
            return value == self.text
        if self.compiled_text_regex:
            return bool(self.compiled_text_regex.fullmatch(value))
        return False

    def match_description(self, value: str) -> bool:
        if not value:
            return False
        if self.description is not None:
            return value == self.description
        if self.compiled_description_regex:
            return bool(self.compiled_description_regex.fullmatch(value))
        return False

    def match(self, info: dict) -> bool:
        text = info.get("text") or ""
        description = info.get("contentDescription") or ""

        text_matched = (
            self.match_text(text)
            if (self.text is not None or self.text_regex)
            else False
        )

        desc_matched = (
            self.match_description(description)
            if (self.description is not None or self.description_regex)
            else False
        )

        return text_matched or desc_matched

    def get_action_type(self) -> str:
        return self.action.get("type", "click")

    def get_action_target(self) -> dict:
        target = self.action.get("target")
        if isinstance(target, dict):
            return target
        return {}


class WatcherRule:
    def __init__(self, rules: list[dict]):
        self.items = [WatcherRuleItem(item) for item in rules]

    def build_text_pattern(self):
        patterns = []
        for item in self.items:
            if item.text is not None:
                patterns.append(re.escape(item.text))
            elif item.text_regex:
                patterns.append(item.text_regex)
        return "|".join(patterns) if patterns else None

    def build_description_pattern(self):
        patterns = []
        for item in self.items:
            if item.description is not None:
                patterns.append(re.escape(item.description))
            elif item.description_regex:
                patterns.append(item.description_regex)
        return "|".join(patterns) if patterns else None

    def match_item(self, info: dict):
        for item in self.items:
            if item.match(info):
                return item
        return None
