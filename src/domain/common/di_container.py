#src/domain/common/di_container.py

"""
Simple dependency injection container for the application.

This container manages service registrations and resolutions,
allowing for clean dependency management throughout the application.
"""
from typing import Dict, Any, Type, TypeVar, Callable, Optional, List
import inspect


T = TypeVar('T')
TBase = TypeVar('TBase')


class DIContainer:
    """
    Simple dependency injection container.

    Manages service registrations and handles dependency resolution.
    """

    def __init__(self):
        """Initialize the container with empty registrations."""
        self._instance_registrations = {}
        self._factory_registrations = {}
        self._resolving = set()  # Tracks types being resolved to detect circular dependencies

    def register_instance(self, base_type: Type[TBase], instance: TBase) -> None:
        """
        Register an instance to be returned whenever the base_type is requested.

        Args:
            base_type: The type to register (typically an interface)
            instance: The instance to return
        """
        self._instance_registrations[base_type] = instance

    def register_factory(self, base_type: Type[TBase], factory: Callable[[], TBase]) -> None:
        """
        Register a factory function that will be called to create instances.

        Args:
            base_type: The type to register (typically an interface)
            factory: A function that creates and returns an instance
        """
        self._factory_registrations[base_type] = factory

    def resolve(self, base_type: Type[T]) -> T:
        """
        Resolve a type to its registered instance or create a new instance.

        Args:
            base_type: The type to resolve

        Returns:
            An instance of the requested type

        Raises:
            ValueError: If the type is not registered or there's a circular dependency
        """
        # Check for circular dependencies
        if base_type in self._resolving:
            raise ValueError(f"Circular dependency detected while resolving {base_type.__name__}")

        # Check if we have an instance registration
        if base_type in self._instance_registrations:
            return self._instance_registrations[base_type]

        # Check if we have a factory registration
        if base_type in self._factory_registrations:
            self._resolving.add(base_type)
            try:
                factory = self._factory_registrations[base_type]
                instance = factory()
                return instance
            finally:
                self._resolving.remove(base_type)

        # No registration found
        raise ValueError(f"No registration found for {base_type.__name__}")

    def resolve_all(self, base_type: Type[T]) -> List[T]:
        """
        Resolve all instances that implement the given type.

        Args:
            base_type: The base type to look for

        Returns:
            A list of all instances implementing the base type
        """
        instances = []

        # Add direct instance
        if base_type in self._instance_registrations:
            instances.append(self._instance_registrations[base_type])

        # Add factory-created instance if available
        if base_type in self._factory_registrations:
            self._resolving.add(base_type)
            try:
                factory = self._factory_registrations[base_type]
                instance = factory()
                instances.append(instance)
            finally:
                self._resolving.remove(base_type)

        return instances