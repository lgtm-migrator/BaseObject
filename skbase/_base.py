# -*- coding: utf-8 -*-
# copyright: skbase developers, BSD-3-Clause License (see LICENSE file)
# Elements of BaseObject re-use code developed in scikit-learn. These elements
# are copyrighted by the scikit-learn developers, BSD-3-Clause License. For
# conditions see https://github.com/scikit-learn/scikit-learn/blob/main/COPYING
"""Base class template for objects and fittable objects.

templates in this module:

    BaseObject - object with parameters and tags
    BaseEstimator - BaseObject that can be fitted

Interface specifications below.

---

    class name: BaseObject

Parameter inspection and setter methods
    inspect parameter values      - get_params()
    setting parameter values      - set_params(**params)
    list of parameter names       - get_param_names()
    dict of parameter defaults    - get_param_defaults()

Tag inspection and setter methods
    inspect tags (all)            - get_tags()
    inspect tags (one tag)        - get_tag(tag_name: str, tag_value_default=None)
    inspect tags (class method)   - get_class_tags()
    inspect tags (one tag, class) - get_class_tag(tag_name:str, tag_value_default=None)
    setting dynamic tags          - set_tag(**tag_dict: dict)
    set/clone dynamic tags        - clone_tags(estimator, tag_names=None)

Blueprinting: resetting and cloning, post-init state with same hyper-parameters
    reset estimator to post-init  - reset()
    cloneestimator (copy&reset)   - clone()

Testing with default parameters methods
    getting default parameters (all sets)         - get_test_params()
    get one test instance with default parameters - create_test_instance()
    get list of all test instances plus name list - create_test_instances_and_names()
---

    class name: BaseEstimator

Provides all interface points of BaseObject, plus:

Parameter inspection:
    fitted parameter inspection - get_fitted_params()

State:
    fitted model/strategy   - by convention, any attributes ending in "_"
    fitted state flag       - is_fitted (property)
    fitted state check      - check_is_fitted (raises error if not is_fitted)
"""

__author__ = ["mloning", "RNKuhns", "fkiraly"]
__all__ = ["BaseEstimator", "BaseObject"]

import inspect
import warnings
from collections import defaultdict
from copy import deepcopy

from sklearn import clone
from sklearn.base import BaseEstimator as _BaseEstimator

from skbase._exceptions import NotFittedError


class BaseObject(_BaseEstimator):
    """Base class for parametric objects with sktime style tag interface.

    Extends scikit-learn's BaseEstimator to include sktime style interface for tags.
    """

    def __init__(self):
        self._tags_dynamic = {}
        super(BaseObject, self).__init__()

    def reset(self):
        """Reset the object to a clean post-init state.

        Using reset, runs __init__ with current values of hyper-parameters
        (result of get_params). This Removes any object attributes, except:

            - hyper-parameters = arguments of __init__
            - object attributes containing double-underscores, i.e., the string "__"

        Class and object methods, and class attributes are also unaffected.

        Returns
        -------
        self
            Instance of class reset to a clean post-init state but retaining
            the current hyper-parameter values.

        Notes
        -----
        Equivalent to sklearn.clone but overwrites self. After self.reset()
        call, self is equal in value to `type(self)(**self.get_params(deep=False))`
        """
        # retrieve parameters to copy them later
        params = self.get_params(deep=False)

        # delete all object attributes in self
        attrs = [attr for attr in dir(self) if "__" not in attr]
        cls_attrs = list(dir(type(self)))
        self_attrs = set(attrs).difference(cls_attrs)
        for attr in self_attrs:
            delattr(self, attr)

        # run init with a copy of parameters self had at the start
        self.__init__(**params)

        return self

    def clone(self):
        """Obtain a clone of the object with same hyper-parameters.

        A clone is a different object without shared references, in post-init state.
        This function is equivalent to returning sklearn.clone of self.

        Notes
        -----
        Also equal in value to `type(self)(**self.get_params(deep=False))`.
        """
        return clone(self)

    @classmethod
    def _get_init_signature(cls):
        """Get class init sigature.

        Useful in parameter inspection.

        Returns
        -------
        List
            The inspected parameter objects (including defaults).

        Raises
        ------
        RuntimeError if cls has varargs in __init__.
        """
        # fetch the constructor or the original constructor before
        # deprecation wrapping if any
        init = getattr(cls.__init__, "deprecated_original", cls.__init__)
        if init is object.__init__:
            # No explicit constructor to introspect
            return []

        # introspect the constructor arguments to find the model parameters
        # to represent
        init_signature = inspect.signature(init)

        # Consider the constructor parameters excluding 'self'
        parameters = [
            p
            for p in init_signature.parameters.values()
            if p.name != "self" and p.kind != p.VAR_KEYWORD
        ]
        for p in parameters:
            if p.kind == p.VAR_POSITIONAL:
                raise RuntimeError(
                    "scikit-learn compatible estimators should always "
                    "specify their parameters in the signature"
                    " of their __init__ (no varargs)."
                    " %s with constructor %s doesn't "
                    " follow this convention." % (cls, init_signature)
                )
        return parameters

    @classmethod
    def get_param_names(cls):
        """Get object's parameter names.

        Returns
        -------
        param_names: list[str]
            Alphabetically sorted list of parameter names of cls.
        """
        parameters = cls._get_init_signature()
        param_names = sorted([p.name for p in parameters])
        return param_names

    @classmethod
    def get_param_defaults(cls):
        """Get object's parameter defaults.

        Returns
        -------
        default_dict: dict[str, Any]
            Keys are all parameters of cls that have a default defined in __init__
            values are the defaults, as defined in __init__.
        """
        parameters = cls._get_init_signature()
        default_dict = {
            x.name: x.default for x in parameters if x.default != inspect._empty
        }
        return default_dict

    def set_params(self, **params):
        """Set the parameters of this object.

        The method works on simple estimators as well as on nested objects.
        The latter have parameters of the form ``<component>__<parameter>`` so
        that it's possible to update each component of a nested object.

        Parameters
        ----------
        **params : dict
            BaseObject parameters.

        Returns
        -------
        self
            Reference to self (after parameters have been set).
        """
        if not params:
            # Simple optimization to gain speed (inspect is slow)
            return self
        valid_params = self.get_params(deep=True)

        nested_params = defaultdict(dict)  # grouped by prefix
        for key, value in params.items():
            key, delim, sub_key = key.partition("__")
            if key not in valid_params:
                raise ValueError(
                    "Invalid parameter %s for object %s. "
                    "Check the list of available parameters "
                    "with `object.get_params().keys()`." % (key, self)
                )

            if delim:
                nested_params[key][sub_key] = value
            else:
                setattr(self, key, value)
                valid_params[key] = value

        self.reset()

        # recurse in components
        for key, sub_params in nested_params.items():
            valid_params[key].set_params(**sub_params)

        return self

    @classmethod
    def get_class_tags(cls):
        """Get class tags from the class and all its parent classes.

        Retrieves tag: value pairs from _tags class attribute. Does not return
        information from dynamic tags (set via set_tags or clone_tags)
        that are defined on instances.

        Returns
        -------
        collected_tags : dict
            Dictionary of class tag name: tag value pairs. Collected from _tags
            class attribute via nested inheritance.
        """
        collected_tags = {}

        # We exclude the last two parent classes: sklearn.base.BaseEstimator and
        # the basic Python object.
        for parent_class in reversed(inspect.getmro(cls)[:-2]):
            if hasattr(parent_class, "_tags"):
                # Need the if here because mixins might not have _more_tags
                # but might do redundant work in estimators
                # (i.e. calling more tags on BaseEstimator multiple times)
                more_tags = parent_class._tags
                collected_tags.update(more_tags)

        return deepcopy(collected_tags)

    @classmethod
    def get_class_tag(cls, tag_name, tag_value_default=None):
        """Get a class tag's value.

        Does not return information from dynamic tags (set via set_tags or clone_tags)
        that are defined on instances.

        Parameters
        ----------
        tag_name : str
            Name of tag value.
        tag_value_default : any
            Default/fallback value if tag is not found.

        Returns
        -------
        tag_value :
            Value of the `tag_name` tag in self. If not found, returns
            `tag_value_default`.
        """
        collected_tags = cls.get_class_tags()

        return collected_tags.get(tag_name, tag_value_default)

    def get_tags(self):
        """Get tags from estimator class and dynamic tag overrides.

        Returns
        -------
        collected_tags : dict
            Dictionary of tag name : tag value pairs. Collected from _tags
            class attribute via nested inheritance and then any overrides
            and new tags from _tags_dynamic object attribute.
        """
        collected_tags = self.get_class_tags()

        if hasattr(self, "_tags_dynamic"):
            collected_tags.update(self._tags_dynamic)

        return deepcopy(collected_tags)

    def get_tag(self, tag_name, tag_value_default=None, raise_error=True):
        """Get tag value from estimator class and dynamic tag overrides.

        Parameters
        ----------
        tag_name : str
            Name of tag to be retrieved
        tag_value_default : any type, optional; default=None
            Default/fallback value if tag is not found
        raise_error : bool
            whether a ValueError is raised when the tag is not found

        Returns
        -------
        tag_value : Any
            Value of the `tag_name` tag in self. If not found, returns an error if
            `raise_error` is True, otherwise it returns `tag_value_default`.

        Raises
        ------
        ValueError if raise_error is True i.e. if `tag_name` is not in
        self.get_tags().keys()
        """
        collected_tags = self.get_tags()

        tag_value = collected_tags.get(tag_name, tag_value_default)

        if raise_error and tag_name not in collected_tags.keys():
            raise ValueError(f"Tag with name {tag_name} could not be found.")

        return tag_value

    def set_tags(self, **tag_dict):
        """Set dynamic tags to given values.

        Parameters
        ----------
        **tag_dict : dict
            Dictionary of tag name: tag value pairs.

        Returns
        -------
        Self
            Reference to self.

        Notes
        -----
        Changes object state by settting tag values in tag_dict as dynamic tags in self.
        """
        tag_update = deepcopy(tag_dict)
        if hasattr(self, "_tags_dynamic"):
            self._tags_dynamic.update(tag_update)
        else:
            self._tags_dynamic = tag_update

        return self

    def clone_tags(self, estimator, tag_names=None):
        """Clone tags from another estimator as dynamic override.

        Parameters
        ----------
        estimator : estimator inheriting from :class:BaseEstimator
        tag_names : str or list of str, default = None
            Names of tags to clone. If None then all tags in estimator are used
            as `tag_names`.

        Returns
        -------
        Self :
            Reference to self.

        Notes
        -----
        Changes object state by setting tag values in tag_set from estimator as
        dynamic tags in self.
        """
        tags_est = deepcopy(estimator.get_tags())

        # if tag_set is not passed, default is all tags in estimator
        if tag_names is None:
            tag_names = tags_est.keys()
        else:
            # if tag_set is passed, intersect keys with tags in estimator
            if not isinstance(tag_names, list):
                tag_names = [tag_names]
            tag_names = [key for key in tag_names if key in tags_est.keys()]

        update_dict = {key: tags_est[key] for key in tag_names}

        self.set_tags(**update_dict)

        return self

    @classmethod
    def get_test_params(cls, parameter_set="default"):
        """Return testing parameter settings for the estimator.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        params : dict or list of dict, default = {}
            Parameters to create testing instances of the class
            Each dict are parameters to construct an "interesting" test instance, i.e.,
            `MyClass(**params)` or `MyClass(**params[i])` creates a valid test instance.
            `create_test_instance` uses the first (or only) dictionary in `params`
        """
        # if non-default parameters are required, but none have been found, raise error
        if hasattr(cls, "_required_parameters"):
            required_parameters = getattr(cls, "required_parameters", [])
            if len(required_parameters) > 0:
                raise ValueError(
                    f"Estimator: {cls} requires "
                    f"non-default parameters for construction, "
                    f"but none were given. Please set them "
                    f"as given in the extension template"
                )

        # construct with parameter configuration for testing, otherwise construct with
        # default parameters (empty dict)
        params = {}
        return params

    @classmethod
    def create_test_instance(cls, parameter_set="default"):
        """Construct Estimator instance if possible.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        instance : instance of the class with default parameters

        Notes
        -----
        `get_test_params` can return dict or list of dict.
        This function takes first or single dict that get_test_params returns, and
        constructs the object with that.
        """
        if "parameter_set" in inspect.getfullargspec(cls.get_test_params).args:
            params = cls.get_test_params(parameter_set=parameter_set)
        else:
            params = cls.get_test_params()

        if isinstance(params, list):
            if isinstance(params[0], dict):
                params = params[0]
            else:
                raise TypeError(
                    "get_test_params should either return a dict or list of dict."
                )
        elif isinstance(params, dict):
            pass
        else:
            raise TypeError(
                "get_test_params should either return a dict or list of dict."
            )

        return cls(**params)

    @classmethod
    def create_test_instances_and_names(cls, parameter_set="default"):
        """Create list of all test instances and a list of names for them.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        objs : list of instances of cls
            i-th instance is cls(**cls.get_test_params()[i])
        names : list of str, same length as objs
            i-th element is name of i-th instance of obj in tests
            convention is {cls.__name__}-{i} if more than one instance
            otherwise {cls.__name__}
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.
        """
        if "parameter_set" in inspect.getfullargspec(cls.get_test_params).args:
            param_list = cls.get_test_params(parameter_set=parameter_set)
        else:
            param_list = cls.get_test_params()

        objs = []
        if not isinstance(param_list, (dict, list)):
            raise RuntimeError(
                f"Error in {cls.__name__}.get_test_params, "
                "return must be param dict for class, or list thereof"
            )
        if isinstance(param_list, dict):
            param_list = [param_list]
        for params in param_list:
            if not isinstance(params, dict):
                raise RuntimeError(
                    f"Error in {cls.__name__}.get_test_params, "
                    "return must be param dict for class, or list thereof"
                )
            objs += [cls(**params)]

        num_instances = len(param_list)
        if num_instances > 1:
            names = [cls.__name__ + "-" + str(i) for i in range(num_instances)]
        else:
            names = [cls.__name__]

        return objs, names

    @classmethod
    def _has_implementation_of(cls, method):
        """Check if method has a concrete implementation in this class.

        This assumes that having an implementation is equivalent to
            one or more overrides of `method` in the method resolution order.

        Parameters
        ----------
        method : str, name of method to check implementation of

        Returns
        -------
        bool, whether method has implementation in cls
            True if cls.method has been overridden at least once in
                the inheritance tree (according to method resolution order)
        """
        # walk through method resolution order and inspect methods
        #   of classes and direct parents, "adjacent" classes in mro
        mro = inspect.getmro(cls)
        # collect all methods that are not none
        methods = [getattr(c, method, None) for c in mro]
        methods = [m for m in methods if m is not None]

        for i in range(len(methods) - 1):
            # the method has been overridden once iff
            #  at least two of the methods collected are not equal
            #  equivalently: some two adjacent methods are not equal
            overridden = methods[i] != methods[i + 1]
            if overridden:
                return True

        return False

    def is_composite(self):
        """Check if the object is composed of other BaseObjects.

        A composite object is an object which contains objects, as parameters.
        Called on an instance, since this may differ by instance.

        Returns
        -------
        composite: bool
            Whether an object has any parameters whose values
            are BaseObjects.
        """
        # walk through method resolution order and inspect methods
        #   of classes and direct parents, "adjacent" classes in mro
        params = self.get_params(deep=False)
        composite = any(isinstance(x, BaseObject) for x in params.values())

        return composite

    def _components(self, base_class=None):
        """Return references to all state changing BaseObject type attributes.

        This *excludes* the blue-print-like components passed in the __init__.

        Caution: this method returns *references* and not *copies*.
            Writing to the reference will change the respective attribute of self.

        Parameters
        ----------
        base_class : class, optional, default=None, must be subclass of BaseObject
            if not None, sub-sets return dict to only descendants of base_class

        Returns
        -------
        dict with key = attribute name, value = reference to that BaseObject attribute
        dict contains all attributes of self that inherit from BaseObjects, and:
            whose names do not contain the string "__", e.g., hidden attributes
            are not class attributes, and are not hyper-parameters (__init__ args)
        """
        if base_class is None:
            base_class = BaseObject
        if base_class is not None and not inspect.isclass(base_class):
            raise TypeError(f"base_class must be a class, but found {type(base_class)}")
        if base_class is not None and not issubclass(base_class, BaseObject):
            raise TypeError("base_class must be a subclass of BaseObject")

        # retrieve parameter names to exclude them later
        param_names = self.get_params(deep=False).keys()

        # retrieve all attributes that are BaseObject descendants
        attrs = [attr for attr in dir(self) if "__" not in attr]
        cls_attrs = list(dir(type(self)))
        self_attrs = set(attrs).difference(cls_attrs).difference(param_names)

        comp_dict = {x: getattr(self, x) for x in self_attrs}
        comp_dict = {x: y for (x, y) in comp_dict.items() if isinstance(y, base_class)}

        return comp_dict


class TagAliaserMixin:
    """Mixin class for tag aliasing and deprecation of old tags.

    To deprecate tags, add the TagAliaserMixin to BaseObject or BaseEstimator.
    alias_dict contains the deprecated tags, and supports removal and renaming.
        For removal, add an entry "old_tag_name": ""
        For renaming, add an entry "old_tag_name": "new_tag_name"
    deprecate_dict contains the version number of renaming or removal.
        the keys in deprecate_dict should be the same as in alias_dict.
        values in deprecate_dict should be strings, the version of removal/renaming.

    The class will ensure that new tags alias old tags and vice versa, during
    the deprecation period. Informative warnings will be raised whenever the
    deprecated tags are being accessed.

    When removing tags, ensure to remove the removed tags from this class.
    If no tags are deprecated anymore (e.g., all deprecated tags are removed/renamed),
    ensure toremove this class as a parent of BaseObject or BaseEstimator.
    """

    # dictionary of aliases
    # key = old tag; value = new tag, aliased by old tag
    # override this in a child class
    alias_dict = {"old_tag": "new_tag", "tag_to_remove": ""}

    # dictionary of removal version
    # key = old tag; value = version in which tag will be removed, as string
    deprecate_dict = {"old_tag": "0.12.0", "tag_to_remove": "99.99.99"}

    def __init__(self):
        super(TagAliaserMixin, self).__init__()

    @classmethod
    def get_class_tags(cls):
        """Get class tags from estimator class and all its parent classes.

        Returns
        -------
        collected_tags : dict
            Dictionary of tag name : tag value pairs. Collected from _tags
            class attribute via nested inheritance. NOT overridden by dynamic
            tags set by set_tags or mirror_tags.
        """
        collected_tags = super(TagAliaserMixin, cls).get_class_tags()
        collected_tags = cls._complete_dict(collected_tags)
        return collected_tags

    @classmethod
    def get_class_tag(cls, tag_name, tag_value_default=None):
        """Get tag value from estimator class (only class tags).

        Parameters
        ----------
        tag_name : str
            Name of tag value.
        tag_value_default : any type
            Default/fallback value if tag is not found.

        Returns
        -------
        tag_value :
            Value of the `tag_name` tag in self. If not found, returns
            `tag_value_default`.
        """
        cls._deprecate_tag_warn([tag_name])
        return super(TagAliaserMixin, cls).get_class_tag(
            tag_name=tag_name, tag_value_default=tag_value_default
        )

    def get_tags(self):
        """Get tags from estimator class and dynamic tag overrides.

        Returns
        -------
        collected_tags : dict
            Dictionary of tag name : tag value pairs. Collected from _tags
            class attribute via nested inheritance and then any overrides
            and new tags from _tags_dynamic object attribute.
        """
        collected_tags = super(TagAliaserMixin, self).get_tags()
        collected_tags = self._complete_dict(collected_tags)
        return collected_tags

    def get_tag(self, tag_name, tag_value_default=None, raise_error=True):
        """Get tag value from estimator class and dynamic tag overrides.

        Parameters
        ----------
        tag_name : str
            Name of tag to be retrieved
        tag_value_default : any type, optional; default=None
            Default/fallback value if tag is not found
        raise_error : bool
            whether a ValueError is raised when the tag is not found

        Returns
        -------
        tag_value :
            Value of the `tag_name` tag in self. If not found, returns an error if
            raise_error is True, otherwise it returns `tag_value_default`.

        Raises
        ------
        ValueError if raise_error is True i.e. if tag_name is not in self.get_tags(
        ).keys()
        """
        self._deprecate_tag_warn([tag_name])
        return super(TagAliaserMixin, self).get_tag(
            tag_name=tag_name,
            tag_value_default=tag_value_default,
            raise_error=raise_error,
        )

    def set_tags(self, **tag_dict):
        """Set dynamic tags to given values.

        Parameters
        ----------
        tag_dict : dict
            Dictionary of tag name : tag value pairs.

        Returns
        -------
        Self :
            Reference to self.

        Notes
        -----
        Changes object state by settting tag values in tag_dict as dynamic tags
        in self.
        """
        self._deprecate_tag_warn(tag_dict.keys())

        tag_dict = self._complete_dict(tag_dict)
        super(TagAliaserMixin, self).set_tags(**tag_dict)
        return self

    @classmethod
    def _complete_dict(cls, tag_dict):
        """Add all aliased and aliasing tags to the dictionary."""
        alias_dict = cls.alias_dict
        deprecated_tags = set(tag_dict.keys()).intersection(alias_dict.keys())
        new_tags = set(tag_dict.keys()).intersection(alias_dict.values())

        if len(deprecated_tags) > 0 or len(new_tags) > 0:
            new_tag_dict = deepcopy(tag_dict)
            # for all tag strings being set, write the value
            #   to all tags that could *be aliased by* the string
            #   and all tags that could be *aliasing* the string
            # this way we ensure upwards and downwards compatibility
            for old_tag, new_tag in alias_dict.items():
                for tag in tag_dict:
                    if tag == old_tag and new_tag != "":
                        new_tag_dict[new_tag] = tag_dict[tag]
                    if tag == new_tag:
                        new_tag_dict[old_tag] = tag_dict[tag]
            return new_tag_dict
        else:
            return tag_dict

    @classmethod
    def _deprecate_tag_warn(cls, tags):
        """Print warning message for tag deprecation.

        Parameters
        ----------
        tags : list of str

        Raises
        ------
        DeprecationWarning for each tag in tags that is aliased by cls.alias_dict
        """
        for tag_name in tags:
            if tag_name in cls.alias_dict.keys():
                version = cls.deprecate_dict[tag_name]
                new_tag = cls.alias_dict[tag_name]
                msg = f'tag "{tag_name}" will be removed in sktime version {version}'
                if new_tag != "":
                    msg += (
                        f' and replaced by "{new_tag}", please use "{new_tag}" instead'
                    )
                else:
                    msg += ', please remove code that access or sets "{tag_name}"'
                warnings.warn(msg, category=DeprecationWarning)


class BaseEstimator(BaseObject):
    """Base class for estimators with scikit-learn and sktime design patterns.

    Extends BaseObject to include basic functionality for fittable estimators.
    """

    def __init__(self):
        """Construct BaseEstimator."""
        self._is_fitted = False
        super(BaseEstimator, self).__init__()

    @property
    def is_fitted(self):
        """Whether `fit` has been called.

        Inspects object's `_is_fitted` attribute that should initialize to False
        during object construction, and be set to True in calls to an object's
        `fit` method.

        Returns
        -------
        bool
            Whether the estimator has been `fit`.
        """
        return self._is_fitted

    def check_is_fitted(self):
        """Check if the estimator has been fitted.

        Inspects object's `_is_fitted` attribute that should initialize to False
        during object construction, and be set to True in calls to an object's
        `fit` method.

        Raises
        ------
        NotFittedError
            If the estimator has not been fitted yet.
        """
        if not self.is_fitted:
            raise NotFittedError(
                f"This instance of {self.__class__.__name__} has not "
                f"been fitted yet; please call `fit` first."
            )
