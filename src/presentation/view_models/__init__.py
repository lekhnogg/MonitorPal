# src/presentation/view_models/__init__.py
from typing import Callable, Dict, Any, List, Optional, TypeVar, Generic, Set

T = TypeVar('T')

class BaseViewModel:
    """Base class for all ViewModels with property change notification."""
    
    def __init__(self):
        self._property_observers: Dict[str, Set[Callable[[str, Any], None]]] = {}
    
    def notify_property_changed(self, property_name: str, value: Any) -> None:
        """Notify observers that a property has changed."""
        if property_name in self._property_observers:
            for callback in self._property_observers[property_name]:
                callback(property_name, value)
    
    def observe_property(self, property_name: str, callback: Callable[[str, Any], None]) -> None:
        """Register a callback to be notified when property changes."""
        if property_name not in self._property_observers:
            self._property_observers[property_name] = set()
        self._property_observers[property_name].add(callback)
    
    def unobserve_property(self, property_name: str, callback: Callable[[str, Any], None]) -> None:
        """Remove a property change callback."""
        if property_name in self._property_observers and callback in self._property_observers[property_name]:
            self._property_observers[property_name].remove(callback)