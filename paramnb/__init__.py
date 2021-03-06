"""
Jupyter notebook interface for Param (https://github.com/ioam/param).

Given a Parameterized object, displays a box with an ipywidget for each
Parameter, allowing users to view and and manipulate Parameter values
from within a Jupyter/IPython notebook.
"""

import sys
import types
import itertools

from collections import OrderedDict

from IPython import get_ipython
from IPython.display import display, Javascript

import ipywidgets

import param
from param.parameterized import classlist

__version__ = param.Version(release=(1,0,0), fpath=__file__,
                             commit="$Format:%h$", reponame='paramnb')

if sys.version_info.major == 3:
    unicode = str
    basestring = str


def FloatWidget(*args, **kw):
    """Returns appropriate slider or text boxes depending on bounds"""
    has_bounds = not (kw['min'] is None or kw['max'] is None)
    return (ipywidgets.FloatSlider if has_bounds else ipywidgets.FloatText)(*args,**kw)


def IntegerWidget(*args, **kw):
    """Returns appropriate slider or text boxes depending on bounds"""
    has_bounds = not (kw['min'] is None or kw['max'] is None)
    return (ipywidgets.IntSlider if has_bounds else ipywidgets.IntText)(*args,**kw)


def TextWidget(*args, **kw):
    """Forces a parameter value to be text"""
    kw['value'] = str(kw['value'])
    return ipywidgets.Text(*args,**kw)


def ActionButton(*args, **kw):
    """Returns a ipywidgets.Button executing a paramnb.Action."""
    kw['description'] = str(kw['name'])
    value = kw["value"]
    w = ipywidgets.Button(*args,**kw)
    if value: w.on_click(value)
    return w

# Maps from Parameter type to ipython widget types with any options desired
ptype2wtype = {
    param.Parameter:     TextWidget,
    param.Selector:      ipywidgets.Dropdown,
    param.Boolean:       ipywidgets.Checkbox,
    param.Number:        FloatWidget,
    param.Integer:       IntegerWidget,
    param.ListSelector:  ipywidgets.SelectMultiple,
    param.Action:        ActionButton,
}


def wtype(pobj):
    if pobj.constant: # Ensure constant parameters cannot be edited
        return ipywidgets.HTML
    for t in classlist(type(pobj))[::-1]:
        if t in ptype2wtype:
            return ptype2wtype[t]


def run_next_cells(n):
    if n=='all':
        n = 'NaN'
    elif n<1:
        return

    js_code = """
       var num = {0};
       var run = false;
       var current = $(this)[0];
       $.each(IPython.notebook.get_cells(), function (idx, cell) {{
          if ((cell.output_area === current) && !run) {{
             run = true;
          }} else if ((cell.cell_type == 'code') && !(num < 1) && run) {{
             cell.execute();
             num = num - 1;
          }}
       }});
    """.format(n)

    display(Javascript(js_code))


def estimate_label_width(labels):
    """
    Given a list of labels, estimate the width in pixels
    and return in a format accepted by CSS.
    Necessarily an approximation, since the font is unknown
    and is usually proportionally spaced.
    """
    max_length = max([len(l) for l in labels])
    return "{0}px".format(max(60,int(max_length*7.5)))


def named_objs(objlist):
    """
    Given a list of objects, returns a dictionary mapping from
    string name for the object to the object itself.
    """
    objs = OrderedDict()
    for k, obj in objlist:
        if hasattr(k, '__name__'):
            k = k.__name__
        elif sys.version_info < (3,0) and isinstance(k, basestring):
            k = unicode(k.decode('utf-8'))
        else:
            k = unicode(k)
        objs[k] = obj
    return objs


class Widgets(param.ParameterizedFunction):

    callback = param.Callable(default=None, doc="""
        Custom callable to execute on button press
        (if `button`) else whenever a widget is changed,
        Should accept a Parameterized object argument.""")

    next_n = param.Parameter(default=0, doc="""
        When executing cells, integer number to execute (or 'all').
        A value of zero means not to control cell execution.""")

    on_init = param.Boolean(default=False, doc="""
        Whether to do the action normally taken (executing cells
        and/or calling a callable) when first instantiating this
        object.""")

    button = param.Boolean(default=False, doc="""
        Whether to show a button to control cell execution.
        If false, will execute `next` cells on any widget
        value change.""")

    label_width = param.Parameter(default=estimate_label_width, doc="""
        Width of the description for parameters in the list, using any
        string specification accepted by CSS (e.g. "100px" or "50%").
        If set to a callable, will call that function using the list of
        all labels to get the value.""")

    tooltips = param.Boolean(default=True, doc="""
        Whether to add tooltips to the parameter names to show their
        docstrings.""")


    def __call__(self, parameterized, **params):
        self.p = param.ParamOverrides(self, params)
        self._widgets = {}
        self.parameterized = parameterized

        widgets = self.widgets()
        layout = ipywidgets.Layout(display='flex', flex_flow='row')
        vbox = ipywidgets.VBox(children=widgets, layout=layout)

        display(vbox)

        if self.p.on_init:
            self.execute_widget(None)

    def _make_widget(self, p_name):
        p_obj = self.parameterized.params(p_name)
        widget_class = wtype(p_obj)

        kw = dict(value=getattr(self.parameterized, p_name), tooltip=p_obj.doc)
        kw['name'] = p_name

        if hasattr(p_obj, 'get_range'):
            kw['options'] = named_objs(p_obj.get_range().items())

        if hasattr(p_obj, 'get_soft_bounds'):
            kw['min'], kw['max'] = p_obj.get_soft_bounds()

        w = widget_class(**kw)

        def change_event(event):
            new_values = event['new']
            setattr(self.parameterized, p_name, new_values)
            if not self.p.button:
                self.execute(None)
        w.observe(change_event, 'value')

        # Hack ; should be part of Widget classes
        if hasattr(p_obj,"path"):
            def path_change_event(event):
                new_values = event['new']
                p_obj = self.parameterized.params(p_name)
                p_obj.path = new_values
                p_obj.update()

                # Update default value in widget, ensuring it's always a legal option
                selector = self._widgets[p_name].children[1]
                defaults = p_obj.default
                if not issubclass(type(defaults),list):
                    defaults = [defaults]
                selector.options.update(named_objs(zip(defaults,defaults)))
                selector.value=p_obj.default
                selector.options=named_objs(p_obj.get_range().items())

                if p_obj.objects and not self.p.button:
                    self.execute(None)

            path_w = ipywidgets.Text(value=p_obj.path)
            path_w.observe(path_change_event, 'value')
            w = ipywidgets.VBox(children=[path_w,w])

        return w


    def widget(self, param_name):
        """Get widget for param_name"""
        if param_name not in self._widgets:
            self._widgets[param_name] = self._make_widget(param_name)
        return self._widgets[param_name]


    def execute(self, event):
        run_next_cells(self.p.next_n)
        if self.p.callback is not None:

            if (sys.version_info < (3,0) and isinstance(self.p.callback, types.UnboundMethodType)
                and  self.p.callback.im_self is self.parameterized):
               self.p.callback()
            else:
                self.p.callback(self.parameterized)

    # Define tooltips, other settings
    preamble = """
        <style>
          .ttip { position: relative; display: inline-block; }
          .ttip .ttiptext { visibility: hidden; background-color: lightgray;
             color: black; border-radius: 6px; padding: 5px; text-align: center;
             position: absolute; left: 103%; top: 0px;
             z-index: 100; min-width: 200px; }
          .ttip:hover .ttiptext { visibility: visible; }
          .widget-dropdown .dropdown-menu { width: 100% }
        </style>
        """

    label_format = """<div class="ttip" style="padding: 5px; width: {0};
                      text-align: right;">{1}</div>"""

    def helptip(self,obj):
        """Return HTML code formatting a tooltip if help is available"""
        helptext = obj.__doc__
        if not self.p.tooltips or not helptext: return ""
        return """<span class="ttiptext">{0}</span>""".format(helptext)


    def widgets(self):
        """Return name,widget boxes for all parameters (i.e., a property sheet)"""

        params = self.parameterized.params().items()
        key_fn = lambda x: x[1].precedence if x[1].precedence else 0
        sorted_precedence = sorted(params, key=key_fn)
        filtered = [(k,p) for (k,p) in sorted_precedence if (p.precedence >= 0)
                    or (p.precedence is None)]
        groups = itertools.groupby(filtered, key=key_fn)
        sorted_groups = [sorted(grp) for (k,grp) in groups]
        ordered_params = [el[0] for group in sorted_groups for el in group]

        # Format name specially
        name = ordered_params.pop(ordered_params.index('name'))
        widgets = [ipywidgets.HTML(self.preamble +
            '<div class="ttip"><b>{0}</b>'.format(self.parameterized.name)+"</div>")]

        label_width=self.p.label_width
        if callable(label_width):
            label_width = label_width(self.parameterized.params().keys())

        def format_name(pname):
            name = self.label_format.format(label_width, pname +
                                            self.helptip(self.parameterized.params(pname)))
            return ipywidgets.HTML(name)

        widgets += [ipywidgets.HBox(children=[format_name(pname),self.widget(pname)])
                   for pname in ordered_params]

        if self.p.button and not (self.p.callback is None and self.p.next_n==0):
            label = 'Run %s' % self.p.next_n if self.p.next_n>0 else "Run"
            display_button = ipywidgets.Button(description=label)
            display_button.on_click(self.execute)
            widgets.append(display_button)

        return widgets
