from typing import *

from collections import defaultdict
from enum import Enum
import inspect
import json
import os
from pathlib import Path
import pickle as pkl
import pydoc
import recordclass
import shutil
import subprocess
import typing_inspect
import yaml

from .BashUtils import BashUtils


class IOUtils:
    """
    Utility functions for I/O.
    """

    # ----------
    # Directory operations

    class cd:
        """
        Change directory. Usage:

        with IOUtils.cd(path):
            <statements>
        # end with

        Using a string path is supported for backward compatibility.
        Using pathlib.Path should be preferred.
        """

        def __init__(self, path: Union[str, Path]):
            if isinstance(path, str):
                path = Path(path)
            # end if
            self.path = path  # Path
            self.old_path = Path.cwd()  # Path
            return

        def __enter__(self):
            os.chdir(self.path)
            return

        def __exit__(self, type, value, tb):
            os.chdir(self.old_path)
            return

    # Deprecated
    # Use pathlib.Path.is_dir() instead
    @classmethod
    def has_dir(cls, dirname) -> bool:
        return os.path.isdir(dirname)

    # Deprecated
    # Use pathlib.Path.mkdir() instead
    @classmethod
    def mk_dir(cls, dirname, mode=0o777,
               is_remove_if_exists: bool = False,
               is_make_parent: bool = True):
        """
        Makes the directory.
        :param dirname: the name of the directory.
        :param mode: mode of the directory.
        :param is_remove_if_exists: if the directory with name already exists, whether to remove.
        :param is_make_parent: if make parent directory if not exists.
        """
        if cls.has_dir(dirname):
            if is_remove_if_exists:
                rm_cmd = "rm {} -rf".format(dirname)
                subprocess.run(["bash", "-c", rm_cmd])
            else:
                return
        # end if
        parent_dir = os.path.dirname(dirname)
        if not cls.has_dir(parent_dir):
            if is_make_parent:
                cls.mk_dir(parent_dir, mode, is_remove_if_exists=False, is_make_parent=True)
            else:
                raise FileNotFoundError("Path not found: {}".format(parent_dir))
        # end if
        os.mkdir(dirname, mode)
        return

    @classmethod
    def rm_dir(cls, path: Path,
        ignore_non_exist: bool = True,
        force: bool = True,
    ):
        """
        Removes the directory.
        :param path: the name of the directory.
        :param ignore_non_exist: ignores error if the directory does not exist.
        :param force: force remove the directory even it's non-empty.
        """
        if path.is_dir():
            if force:
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.rmdir()
            # end if
        else:
            if ignore_non_exist:
                return
            else:
                raise FileNotFoundError("Trying to remove non-exist directory {}".format(path))
            # end if
        # end if
        return

    @classmethod
    def rm(cls, path: Path,
        ignore_non_exist: bool = True,
        force: bool = True,
    ):
        """
        Removes the file/dir.
        :param path: the path to the file/dir to remove.
        :param ignore_non_exist: ignores error if the file/dir does not exist.
        :param force: force remove the file even it's protected / dir even it's non-empty.
        """
        if path.exists():
            if force:
                BashUtils.run(f"rm -rf {path}")
            else:
                BashUtils.run(f"rm -r {path}")
            # end if
        else:
            if ignore_non_exist:
                return
            else:
                raise FileNotFoundError("Trying to remove non-exist file/dir {}".format(path))
            # end if
        # end if
        return

    # ----------
    # File operations

    class Format(Enum):
        txt = 0,
        pkl = 1,
        jsonPretty = 2,
        jsonNoSort = 3,
        json = 4,

        @classmethod
        def from_str(cls, string: str) -> "IOUtils.Format":
            return {
                "pkl": IOUtils.Format.pkl,
                "json": IOUtils.Format.jsonPretty,
                "json-nosort": IOUtils.Format.jsonNoSort,
                "json_nosort": IOUtils.Format.jsonNoSort,
                "json-min": IOUtils.Format.json,
                "json_min": IOUtils.Format.json,
            }.get(string, IOUtils.Format.txt)

        def get_extension(self) -> str:
            return {
                IOUtils.Format.txt: "txt",
                IOUtils.Format.pkl: "pkl",
                IOUtils.Format.jsonPretty: "json",
                IOUtils.Format.jsonNoSort: "json",
                IOUtils.Format.json: "json",
            }.get(self, "unknown")

    IO_FORMATS: Dict[Format, Dict] = defaultdict(lambda: {
        "mode": "t",
        "dumpf": (lambda obj, f: f.write(obj)),
        "loadf": (lambda f: f.read())
    })
    # pickle (python serialized object)
    IO_FORMATS[Format.pkl]["mode"] = "b"
    IO_FORMATS[Format.pkl]["dumpf"] = lambda obj, f: pkl.dump(obj, f, protocol=pkl.HIGHEST_PROTOCOL)
    IO_FORMATS[Format.pkl]["loadf"] = lambda f: pkl.load(f)
    # json (human readable version)
    IO_FORMATS[Format.jsonPretty]["dumpf"] = lambda obj, f: json.dump(obj, f, indent=4, sort_keys=True)
    IO_FORMATS[Format.jsonPretty]["loadf"] = lambda f: yaml.load(f, Loader=yaml.FullLoader)  # allows some format errors (e.g., trailing commas)
    # json (human readable version)
    IO_FORMATS[Format.jsonNoSort]["dumpf"] = lambda obj, f: json.dump(obj, f, indent=4)
    IO_FORMATS[Format.jsonNoSort]["loadf"] = lambda f: yaml.load(f, Loader=yaml.FullLoader)  # allows some format errors (e.g., trailing commas)
    # json_min (minimize size, operation with code only)
    IO_FORMATS[Format.json]["dumpf"] = lambda obj, f: json.dump(obj, f, sort_keys=True)
    IO_FORMATS[Format.json]["loadf"] = lambda f: json.load(f)

    @classmethod
    def dump(cls, file_path: Union[str, Path], obj: object, fmt: Union[Format, str] = Format.jsonPretty):
        if isinstance(file_path, str):
            file_path = Path(file_path)
        # end if
        file_path.touch(exist_ok=True)

        if isinstance(fmt, str):  fmt = cls.Format.from_str(fmt)
        conf = cls.IO_FORMATS[fmt]

        with open(file_path, "w" + conf["mode"]) as f:
            conf["dumpf"](obj, f)

        return

    @classmethod
    def load(cls, file_path: Union[str, Path], fmt: Union[Format, str] = Format.jsonPretty) -> Any:
        if isinstance(file_path, str):
            file_path = Path(file_path)
        # end if

        if isinstance(fmt, str):  fmt = cls.Format.from_str(fmt)
        conf = cls.IO_FORMATS[fmt]

        try:
            with open(file_path, "r" + conf["mode"]) as f:
                obj = conf["loadf"](f)
            # end with
        except FileNotFoundError as e:
            raise FileNotFoundError(str(e) + " at {}".format(Path.cwd()))
        # end try

        return obj

    @classmethod
    def update_json(cls, file_name, data):
        """
        Updates the json data file. The data should be dict like (support update).
        """
        try:
            orig_data = cls.load(file_name)
        except:
            orig_data = dict()
        # end try
        orig_data.update(data)
        cls.dump(file_name, orig_data)
        return orig_data

    @classmethod
    def extend_json(cls, file_name, data):
        """
        Updates the json data file. The data should be list like (support extend).
        """
        try:
            orig_data = cls.load(file_name)
        except:
            orig_data = list()
        # end try
        orig_data.extend(data)
        cls.dump(file_name, orig_data)
        return orig_data

    JSONFY_FUNC_NAME = "jsonfy"
    DEJSONFY_FUNC_NAME = "dejsonfy"
    JSONFY_ATTR_FIELD_NAME = "jsonfy_attr"

    @classmethod
    def jsonfy(cls, obj):
        """
        Turns an object to a json-compatible data structure.
        A json-compatible data can only have list, dict (with str keys), str, int and float.
        Any object of other classes will be casted through (try each option in order, if applicable):
        1. JSONFY function, which takes no argument and returns a json-compatible data;
           should have the name {@link IOUtils#JSONFY_FUNC_NAME};
        2. JSONFY_ATTR field, which is a dict of attribute name-type pairs, that will be extracted from the object to a dict;
           should have the name {@link IOUtils#JSONFY_ATTR_FIELD_NAME};
        3. cast to a string.
        """
        if obj is None:
            return None
        elif isinstance(obj, (int, float, str, bool)):
            # primitive types
            return obj
        elif isinstance(obj, (list, set, tuple)):  # TODO: support set also in dejsonfy
            # array
            return [cls.jsonfy(item) for item in obj]
        elif isinstance(obj, dict):
            # dict
            return {k: cls.jsonfy(v) for k, v in obj.items()}
        elif isinstance(obj, Enum):
            # Enum
            return obj.value
        elif hasattr(obj, cls.JSONFY_FUNC_NAME):
            # with jsonfy function
            return getattr(obj, cls.JSONFY_FUNC_NAME)()
        elif hasattr(obj, cls.JSONFY_ATTR_FIELD_NAME):
            # with jsonfy_attr annotations
            return {attr: cls.jsonfy(getattr(obj, attr)) for attr in getattr(obj, cls.JSONFY_ATTR_FIELD_NAME).keys()}
        elif isinstance(obj, recordclass.mutabletuple):
            # RecordClass
            return {k: cls.jsonfy(v) for k, v in obj.__dict__.items()}
        else:
            # Last effort: toString
            return repr(obj)

    @classmethod
    def dejsonfy(cls, data, clz=None):
        """
        Turns a json-compatible data structure to an object of class {@code clz}.
        If {@code clz} is not assigned, the data will be casted to dict or list if possible.
        Otherwise the data will be casted to the object through (try each option in order, if applicable):
        1. DEJSONFY function, which takes the data as argument and returns a object;
           should have the name {@link IOUtils#DEJSONFY_FUNC_NAME};
        2. JSONFY_ATTR field, which is a dict of attribute name-type pairs, that will be extracted from the object to a dict;
           should have the name {@link IOUtils#JSONFY_ATTR_FIELD_NAME};
        """
        if isinstance(clz, str):
            clz = pydoc.locate(clz)
        # end if

        if data is None:
            # None value
            return None
        elif clz is not None and typing_inspect.get_origin(clz) == list:
            # List[XXX]
            return [cls.dejsonfy(item, clz.__args__[0]) for item in data]
        elif isinstance(data, list):
            # array
            return [cls.dejsonfy(item, clz) for item in data]
        elif clz is not None and hasattr(clz, cls.DEJSONFY_FUNC_NAME):
            # with dejsonfy function
            return clz.dejsonfy(data)
        elif clz is not None and hasattr(clz, cls.JSONFY_ATTR_FIELD_NAME):
            # with jsonfy_attr annotations
            obj = clz()
            for attr, attr_clz in getattr(clz, cls.JSONFY_ATTR_FIELD_NAME).items():
                if attr in data:
                    setattr(obj, attr, cls.dejsonfy(data[attr], attr_clz))
            # end for, if
            return obj
        elif clz is not None and inspect.isclass(clz) and issubclass(clz, recordclass.mutabletuple):
            # RecordClass
            field_values = dict()
            for f, t in get_type_hints(clz).items():
                if f in data:  field_values[f] = cls.dejsonfy(data.get(f), t)
            # end for
            return clz(**field_values)
        elif clz is not None and inspect.isclass(clz) and issubclass(clz, Enum):
            # Enum
            return clz(data)
        elif isinstance(data, dict):
            # dict
            return {k: cls.dejsonfy(v, clz) for k, v in data.items()}
        else:
            # primitive types / unresolvable things
            if clz is not None:
                try: return clz(data)
                except: pass
            # end if
            return data
