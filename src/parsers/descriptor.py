"""Descriptor parsing and normalization helpers shared by mapping parsers."""

from __future__ import annotations

from collections.abc import Callable
import re

PrimitiveToJvm = {
    "void": "V",
    "byte": "B",
    "char": "C",
    "double": "D",
    "float": "F",
    "int": "I",
    "long": "J",
    "short": "S",
    "boolean": "Z",
}

PrimitiveCodes = frozenset("BCDFIJSZ")
JavaTypePattern = re.compile(r"^(?P<base>[A-Za-z_$][A-Za-z0-9_$.]*)(?P<arrays>(?:\[\])*)$")
ClassNamePattern = re.compile(r"^[A-Za-z0-9_$/.]+$")


class DescriptorError(ValueError):
    """Raised when a JVM or Java type descriptor cannot be parsed."""


def _validate_class_name(name: str, original: str) -> None:
    if not name or not ClassNamePattern.fullmatch(name):
        raise DescriptorError(f"invalid class name {name!r} in descriptor {original!r}")


def _parse_one(
    descriptor: str,
    index: int,
    resolver: Callable[[str], str],
    *,
    allow_void: bool,
) -> tuple[str, int]:
    arrays = 0
    while index < len(descriptor) and descriptor[index] == "[":
        arrays += 1
        index += 1

    if index >= len(descriptor):
        raise DescriptorError(f"missing type in descriptor {descriptor!r}")

    char = descriptor[index]
    if char == "V":
        if not allow_void:
            raise DescriptorError(f"void is not valid in this position in {descriptor!r}")
        if arrays:
            raise DescriptorError(f"void arrays are not valid in {descriptor!r}")
        return "V", index + 1

    if char == "L":
        end = descriptor.find(";", index + 1)
        if end == -1:
            raise DescriptorError(f"unterminated class descriptor in {descriptor!r}")
        name = descriptor[index + 1 : end]
        _validate_class_name(name, descriptor)
        resolved = resolver(name)
        _validate_class_name(resolved, descriptor)
        return "[" * arrays + f"L{resolved};", end + 1

    if char in PrimitiveCodes:
        return "[" * arrays + char, index + 1

    raise DescriptorError(f"invalid descriptor character {char!r} in {descriptor!r}")


def normalize_field_descriptor(descriptor: str, resolver: Callable[[str], str]) -> str:
    """Normalize a field/type descriptor (without method parentheses)."""
    if not descriptor:
        raise DescriptorError("empty descriptor")
    fragment, index = _parse_one(descriptor, 0, resolver, allow_void=False)
    if index != len(descriptor):
        raise DescriptorError(f"trailing data in descriptor {descriptor!r}")
    return fragment


def normalize_method_descriptor(descriptor: str, resolver: Callable[[str], str]) -> str:
    """Normalize a method descriptor, resolving class names through resolver."""
    if not descriptor.startswith("("):
        raise DescriptorError(f"method descriptor must start with '(': {descriptor!r}")

    index = 1
    parameters: list[str] = []
    while True:
        if index >= len(descriptor):
            raise DescriptorError(f"unterminated parameter list in {descriptor!r}")
        if descriptor[index] == ")":
            index += 1
            break
        parameter, index = _parse_one(descriptor, index, resolver, allow_void=False)
        parameters.append(parameter)

    return_type, index = _parse_one(descriptor, index, resolver, allow_void=True)
    if index != len(descriptor):
        raise DescriptorError(f"trailing data in descriptor {descriptor!r}")
    return "(" + "".join(parameters) + ")" + return_type


def normalize_jvm_descriptor(descriptor: str, resolver: Callable[[str], str]) -> str:
    """Normalize either a method descriptor or a field/type descriptor."""
    if descriptor.startswith("("):
        return normalize_method_descriptor(descriptor, resolver)
    return normalize_field_descriptor(descriptor, resolver)


def java_type_to_jvm(type_name: str, resolver: Callable[[str], str]) -> str:
    """Convert an erased Java type as used by ProGuard mappings to a JVM descriptor fragment."""
    match = JavaTypePattern.fullmatch(type_name)
    if not match:
        raise DescriptorError(f"invalid Java type {type_name!r}")

    base = match.group("base")
    arrays = len(match.group("arrays")) // 2
    primitive = PrimitiveToJvm.get(base)
    if primitive is not None:
        if base == "void" and arrays:
            raise DescriptorError("void[] is not a valid type")
        if base == "void":
            return "V"
        return "[" * arrays + primitive

    class_name = resolver(base)
    _validate_class_name(class_name, type_name)
    return "[" * arrays + f"L{class_name};"


def method_descriptor(return_type: str, argument_types: list[str], resolver: Callable[[str], str]) -> str:
    if any(argument == "void" for argument in argument_types):
        raise DescriptorError("void is not a valid parameter type")
    return "(" + "".join(java_type_to_jvm(argument, resolver) for argument in argument_types) + ")" + java_type_to_jvm(return_type, resolver)


def field_descriptor(field_type: str, resolver: Callable[[str], str]) -> str:
    descriptor = java_type_to_jvm(field_type, resolver)
    if descriptor == "V":
        raise DescriptorError("void is not a valid field type")
    return descriptor
