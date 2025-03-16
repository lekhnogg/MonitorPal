# MonitorPal Implementation Plan

This document outlines the implementation plan for the refactored MonitorPal application, detailing the order of components to be implemented and their dependencies.

## Already Implemented

### Core Infrastructure
- ✅ Result class for standardized error handling
- ✅ Dependency Injection container
- ✅ Logger service interface and implementation
- ✅ Config repository interface and implementation
- ✅ Thread service interface and implementation
- ✅ Platform detection service interface and implementation
- ✅ Screenshot service interface and implementation
- ✅ OCR service interface and implementation
- ✅ Monitoring service interface and implementation with region selection and preview
- ✅ Region selection tool with proper coordinate conversion
- ✅ Lockout service interface and implementation
- ✅ Verification service interface and implementation

### Key Integration Points
- ✅ Screenshot capture and OCR workflow
- ✅ Monitoring region selection and preview
- ✅ Platform detection and window management
- ✅ Basic test application with functional tabs
- ✅ Loss threshold detection and lockout sequence
- ✅ Verification of Cold Turkey Blocker blocks

## Next Implementation Steps

### 6. Theme Service (Medium Priority)

The Theme Service will handle the application's visual styling.

**Files to implement:**
- `src/domain/services/i_theme_service.py` - Interface
- `src/infrastructure/ui/theme_service.py` - Implementation

**Dependencies:**
- Logger Service
- Config Repository

**Key functionality:**
- Provide color schemes for different UI elements
- Support light and dark themes
- Apply themes to Qt widgets
- Save/load theme preferences

### 7. Icon Service (Low Priority)

The Icon Service will handle loading and managing application icons.

**Files to implement:**
- `src/domain/services/i_icon_service.py` - Interface
- `src/infrastructure/ui/icon_service.py` - Implementation

**Dependencies:**
- Logger Service
- Theme Service

**Key functionality:**
- Load SVG icons
- Apply theme colors to icons
- Cache icons for performance
- Provide consistent icon sizing

### 8. UI Components (Medium Priority)

Base UI components used throughout the application.

**Files to implement:**
- `src/presentation/components/base_component.py` - Base component class
- `src/presentation/components/platform_selector.py` - Platform selector component
- `src/presentation/components/log_display.py` - Log display component
- Various other reusable components

**Dependencies:**
- Theme Service
- Icon Service

**Key functionality:**
- Provide consistent UI components with proper lifecycle management
- Handle theme changes
- Support dependency injection

### 9. View Models (Medium Priority)

View models for the application's tabs.

**Files to implement:**
- `src/presentation/view_models/main_tab_view_model.py`
- `src/presentation/view_models/config_tab_view_model.py`
- `src/presentation/view_models/monitor_tab_view_model.py`
- `src/presentation/view_models/about_tab_view_model.py`

**Dependencies:**
- Various services depending on the view model

**Key functionality:**
- Provide data and operations for views
- Abstract business logic from UI code
- Handle service interactions

### 10. Views (Low Priority)

The actual UI views/tabs.

**Files to implement:**
- `src/presentation/views/main_window.py`
- `src/presentation/views/main_tab.py`
- `src/presentation/views/config_tab.py`
- `src/presentation/views/monitor_tab.py`
- `src/presentation/views/about_tab.py`

**Dependencies:**
- UI Components
- View Models

**Key functionality:**
- Display UI elements
- Handle user input
- Update based on view model changes

## Implementation Order

The implementation will proceed in the following order:

1. ✅ Screenshot Service
2. ✅ OCR Service
3. ✅ Monitoring Service with region selection and preview
4. ✅ Lockout Service
5. ✅ Verification Service
6. Theme Service
7. Icon Service
8. Base UI Components
9. View Models
10. Views

This order ensures that core functionality is implemented first, followed by UI components.

## Testing Strategy

Each component should have corresponding unit tests in the `tests/unit` directory.
Integration tests should be added for interactions between components in the `tests/integration` directory.

Key integration test scenarios:
- ✅ Screenshot capture and OCR
- ✅ Region selection and preview functionality
- ✅ Basic monitoring functionality
- ✅ Monitoring threshold detection and alerts
- ✅ Lockout sequence
- ✅ Verification process
- Configuration management
- UI component interactions

## Refactoring Approach

The refactoring will follow these principles:

1. **Incremental changes**: Implement and test one component at a time
2. **Dependency injection**: Use the DI container for all dependencies
3. **Interface-based design**: Define interfaces before implementations
4. **Error handling**: Use the Result pattern consistently
5. **Testing**: Write tests alongside implementation
6. **Documentation**: Maintain clear docstrings and comments

## Recent Progress

- Implemented Verification Service to verify Cold Turkey Blocker blocks
- Added verification worker for background thread operations
- Created verification interface that follows the established pattern
- Implemented UI for verification in test_app.py
- Integrated verification with configuration repository