// issue-256: CRA auto-loads this file when it exists and silently does nothing
// when it does not — which is why its ABSENCE was the easy half of AC1 to miss.
// jest-dom's matchers are undefined without it, and that surfaces inside the
// first test as "my assertion is wrong" rather than as a setup error.
import '@testing-library/jest-dom';
