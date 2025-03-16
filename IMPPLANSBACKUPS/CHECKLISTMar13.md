# MonitorPal Threading and Functionality Enhancement Project

## Project Overview

MonitorPal is a risk management tool for traders that monitors trading platforms (Quantower, NinjaTrader, etc.) using OCR to detect P&L values, and triggers lockout sequences when losses exceed predefined thresholds.

## Directory Structure

```
NewLayout/
├── src/
│   ├── application/
│   │   └── app.py
│   ├── domain/
│   │   ├── common/
│   │   │   ├── di_container.py
│   │   │   ├── errors.py
│   │   │   └── result.py
│   │   ├── models/
│   │   │   └── monitoring_result.py
│   │   └── services/
│   │       ├── config_repository.py
│   │       ├── i_logger_service.py
│   │       ├── i_lockout_service.py
│   │       ├── i_monitoring_service.py
│   │       ├── i_ocr_service.py
│   │       ├── i_screenshot_service.py
│   │       ├── i_thread_service.py
│   │       ├── i_verification_service.py
│   │       ├── i_window_management.py
│   │       └── platform_detection_service.py
│   ├── infrastructure/
│   │   ├── config/
│   │   │   └── json_config_repository.py
│   │   ├── logging/
│   │   │   └── logger_service.py
│   │   ├── ocr/
│   │   │   └── tesseract_ocr_service.py
│   │   ├── platform/
│   │   │   ├── lockout_service.py
│   │   │   ├── monitoring_service.py
│   │   │   ├── overlay_window.py
│   │   │   ├── qt_screenshot_service.py
│   │   │   ├── verification_service.py
│   │   │   ├── window_manager.py
│   │   │   ├── windows_platform_detection_service.py
│   │   │   └── workers/
│   │   │       └── verification_worker.py
│   │   └── threading/
│   │       └── qt_thread_service.py
│   └── presentation/
│       └── components/
│           ├── qt_region_selector.py
│           └── ui_components.py
└── utils/
    └── logging_config.py
```

## Comprehensive Testing Checklist

### 1. Core Thread Service Components

- [ ] **Worker Base Class Enhancements**
  - [ ] Implement `CancellationToken` class with proper thread-safety
  - [ ] Implement new `initialize()` method for setup
  - [ ] Implement new `cleanup()` method for resource management
  - [ ] Add proper observer pattern support
  - [ ] Implement exception-based cancellation via `check_cancellation()`
  - [ ] Maintain backward compatibility with existing workers

- [ ] **Qt Thread Service Implementation**
  - [ ] Enhance `WorkerWrapper` with proper signal management
  - [ ] Implement automatic resource cleanup for threads
  - [ ] Add proper cross-thread serialization for results
  - [ ] Prevent memory leaks from circular references
  - [ ] Add periodic task checking
  - [ ] Implement thread-safe task cancellation

- [ ] **Result Pattern Enhancements**
  - [ ] Add thread-safe serialization methods
  - [ ] Add methods to handle complex objects across thread boundaries
  - [ ] Ensure backward compatibility with existing code

### 2. Thread-Specific Tests

- [ ] **Worker Lifecycle Test**
  - [ ] Test initialization phase
  - [ ] Test execution phase 
  - [ ] Test cleanup phase
  - [ ] Test proper execution order

- [ ] **Cancellation Mechanism Test**
  - [ ] Test flag-based cancellation
  - [ ] Test exception-based cancellation
  - [ ] Test cancellation during initialization
  - [ ] Test cancellation during execution
  - [ ] Test cleanup after cancellation

- [ ] **Thread-Safe Results Test**
  - [ ] Test primitive type passing
  - [ ] Test complex object serialization
  - [ ] Test custom class handling
  - [ ] Test large data transfer
  - [ ] Test circular reference handling

- [ ] **Memory Management Test**
  - [ ] Test resource cleanup after normal completion
  - [ ] Test resource cleanup after cancellation
  - [ ] Test resource cleanup after error
  - [ ] Test handling of many concurrent tasks
  - [ ] Test rapid task creation/cancellation

- [ ] **Signal-Slot Connection Test**
  - [ ] Test proper signal connections
  - [ ] Test proper signal disconnections
  - [ ] Test thread-safe callbacks

### 3. Functional Components Tests

- [ ] **Configuration Repository**
  - [ ] Test loading configuration
  - [ ] Test saving configuration 
  - [ ] Test concurrent operations
  - [ ] Test observer pattern for config changes
  - [ ] Test error handling for corrupted files
  - [ ] Test platform-specific settings

- [ ] **Screenshot Service**
  - [ ] Test region selection
  - [ ] Test screenshot capture
  - [ ] Test capturing multiple screenshots concurrently
  - [ ] Test image format conversion
  - [ ] Test saving screenshots to disk
  - [ ] Test memory management for large screenshots

- [ ] **OCR Service**
  - [ ] Test text extraction from images
  - [ ] Test text preprocessing
  - [ ] Test numeric value extraction
  - [ ] Test handling of different font sizes and styles
  - [ ] Test concurrent OCR operations
  - [ ] Test error recovery for partial recognition
  - [ ] Test performance with large images

- [ ] **Monitoring Service**
  - [ ] Test start/stop monitoring
  - [ ] Test threshold detection
  - [ ] Test value parsing from OCR results
  - [ ] Test interval-based checking
  - [ ] Test platform window detection
  - [ ] Test callback handling for status updates
  - [ ] Test error handling during monitoring
  - [ ] Test monitoring history tracking

- [ ] **Lockout Service**
  - [ ] Test platform window activation
  - [ ] Test transparent overlay creation
  - [ ] Test click-through regions for flatten buttons
  - [ ] Test Cold Turkey Blocker integration
  - [ ] Test countdown sequence
  - [ ] Test lockout duration enforcement
  - [ ] Test error handling during lockout
  - [ ] Test cancellation of lockout sequence

- [ ] **Window Management**
  - [ ] Test window detection by title
  - [ ] Test window detection by process ID
  - [ ] Test bringing windows to foreground
  - [ ] Test window visibility checking
  - [ ] Test finding all windows for a process
  - [ ] Test window manipulation functions
  - [ ] Test window process ID retrieval

- [ ] **Platform Detection Service**
  - [ ] Test detection of supported trading platforms
  - [ ] Test window activation for platforms
  - [ ] Test checking if platform window is active
  - [ ] Test getting all windows for a platform
  - [ ] Test error handling for missing platforms

- [ ] **Verification Service**
  - [ ] Test Cold Turkey block verification
  - [ ] Test block addition to verified list
  - [ ] Test block removal from verified list
  - [ ] Test cancellation of verification process
  - [ ] Test persistent storage of verified blocks

### 4. Integration Tests

- [ ] **Configuration → Platform Detection**
  - [ ] Test loading platform settings and detecting windows

- [ ] **Screenshot → OCR Integration**
  - [ ] Test capturing and OCR processing in single workflow
  - [ ] Test error handling across the integration

- [ ] **Monitoring → Lockout Integration**
  - [ ] Test threshold detection triggering lockout
  - [ ] Test complete lockout sequence from monitoring trigger

- [ ] **Window Management → Platform Detection Integration**
  - [ ] Test platform detection using window management functions

- [ ] **Verification → Lockout Integration**
  - [ ] Test verification before allowing lockout

### 5. Stress and Performance Tests

- [ ] **Concurrency Stress Tests**
  - [ ] Test many concurrent workers across services
  - [ ] Test rapid starting/stopping of monitoring
  - [ ] Test parallel screenshot and OCR operations

- [ ] **Memory Usage Tests**
  - [ ] Test memory consumption during extended monitoring
  - [ ] Test memory usage with large screenshots
  - [ ] Test memory leaks in long-running services

- [ ] **CPU Usage Tests**
  - [ ] Test CPU consumption during OCR processing
  - [ ] Test CPU usage during monitoring
  - [ ] Test UI responsiveness under load

- [ ] **Reliability Tests**
  - [ ] Test operation with missing platforms
  - [ ] Test recovery from platform crashes
  - [ ] Test behavior on system resource constraints

## Implementation Notes

1. **Clean Architecture**: All changes should respect the existing clean architecture. Domain interfaces should remain stable, with changes focusing on implementation details in the infrastructure layer.

2. **Backward Compatibility**: Always ensure that existing code continues to work with the enhanced components. Add compatibility layers where needed.

3. **Incremental Implementation**: Implement changes incrementally and test thoroughly before moving on. Start with the core components and then test each modification.

4. **Use Existing Test App**: The existing `test_app.py` contains many useful test scenarios that can be adapted for your mini-tests. Extract the relevant snippets and modify them to work with the enhanced threading components.

5. **Test Before Integration**: Each mini-test should verify a specific aspect of the threading and functional enhancements before integrating changes into the main codebase.

6. **Follow Best Practices**:
   - Use proper thread synchronization
   - Avoid shared mutable state
   - Ensure proper resource cleanup
   - Handle errors consistently
   - Document thread-safety assumptions

## Testing Strategy

1. **Component-Level Testing**
   - Create focused mini-tests for each component
   - Test the threading enhancements in isolation
   - Verify each functional aspect works as expected

2. **Integration Testing**
   - Test interactions between enhanced components
   - Verify the complete workflow with enhanced components

3. **System Testing**
   - Test the entire application with all enhancements
   - Verify that the application functions correctly as a whole

4. **Stress Testing**
   - Subject the application to high loads and extended operation
   - Verify that the enhancements improve stability and performance

When creating mini-tests from the existing `test_app.py`, be sure to adapt them to use the enhanced threading components and focus on testing one specific aspect at a time. Start with basic functionality tests and progressively move to more complex integration scenarios.