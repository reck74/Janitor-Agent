// Janitor ships its screens in the desktop app; this manifest exists only so
// the backend routes mount. The web dashboard route stays hidden and inert.
;(function () {
  var sdk = window.__HERMES_PLUGIN_SDK__
  var plugins = window.__HERMES_PLUGINS__
  if (!sdk || !plugins) return
  plugins.register('janitor', function JanitorDesktopOnly() {
    return sdk.React.createElement('p', null, 'Esta pantalla está en la app de escritorio de Janitor.')
  })
})()
