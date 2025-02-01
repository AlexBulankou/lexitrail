apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: lexitrail-frontend-config
spec:
  healthCheck:
    checkIntervalSec: 15
    timeoutSec: 5
    healthyThreshold: 1
    unhealthyThreshold: 2
    type: HTTP
    requestPath: /
    port: 3000
  redirectToHttps:
    enabled: true
    responseCodeName: MOVED_PERMANENTLY_DEFAULT