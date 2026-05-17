from django import forms


class BootstrapModelForm(forms.ModelForm):
    """ModelForm base class that applies Bootstrap-friendly widget classes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            widget = field.widget
            classes = widget.attrs.get("class", "").split()

            if isinstance(widget, forms.CheckboxInput):
                classes.append("form-check-input")
            elif isinstance(widget, forms.Select):
                classes.append("form-select")
            else:
                classes.append("form-control")

            widget.attrs["class"] = " ".join(dict.fromkeys(classes)).strip()

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 4)
