apiVersion: networking.gke.io/v1beta1
kind: FrontendConfig
metadata:
  name: lexitrail-frontend-frontend-config
spec:
  redirectToHttps:
    enabled: true
    responseCodeName: MOVED_PERMANENTLY_DEFAULT
