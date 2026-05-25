import wrapAnsiModule from 'wrap-ansi'

type WrapAnsiOptions = {
  hard?: boolean
  wordWrap?: boolean
  trim?: boolean
}

type WrapAnsiFn = (input: string, columns: number, options?: WrapAnsiOptions) => string

type WrapAnsiModuleShape = WrapAnsiFn | { default: WrapAnsiFn }

const wrapAnsiBun = typeof Bun !== 'undefined' && typeof Bun.wrapAnsi === 'function' ? Bun.wrapAnsi : null
const wrapAnsiImport = wrapAnsiModule as unknown as WrapAnsiModuleShape
const wrapAnsiNpm: WrapAnsiFn =
  typeof wrapAnsiImport === 'function' ? wrapAnsiImport : wrapAnsiImport.default

const wrapAnsi: WrapAnsiFn = wrapAnsiBun ?? wrapAnsiNpm

export { wrapAnsi }
