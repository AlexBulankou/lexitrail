apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: lexitrail-backend-config
  namespace: ${backend_namespace}
spec:
  healthCheck:
    checkIntervalSec: 15
    timeoutSec: 5
    healthyThreshold: 2
    unhealthyThreshold: 3
    type: HTTP
    requestPath: /health  # Make sure your backend has this endpoint
    port: 80
  timeoutSec: 30