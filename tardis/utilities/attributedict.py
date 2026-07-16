def convert_to_attribute_dict(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            obj[key] = convert_to_attribute_dict(value)
        return AttributeDict(obj)
    elif isinstance(obj, list):
        return [convert_to_attribute_dict(item) for item in obj]
    else:
        return obj


class AttributeDict(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(
                f"{item} is not a valid attribute. Dict contains {str(self)}.",
                name=item,
                obj=self,
            ) from None

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, item):
        try:
            del self[item]
        except KeyError:
            raise AttributeError(
                f"{item} is not a valid attribute. Dict contains {str(self)}.",
                name=item,
                obj=self,
            ) from None

    def __or__(self, other):
        return AttributeDict({**self, **other})
