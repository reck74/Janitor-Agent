const { contextBridge, ipcRenderer } = require('electron')
const prefix = '--janitor-setup-channel='
const channel = process.argv.find(argument => argument.startsWith(prefix))?.slice(prefix.length)
if (!channel || !/^janitor:setup:[0-9a-f-]+$/.test(channel)) throw new Error('Missing Janitor setup channel')
contextBridge.exposeInMainWorld('janitorSetup', Object.freeze({ submit: value => ipcRenderer.invoke(channel, value) }))
