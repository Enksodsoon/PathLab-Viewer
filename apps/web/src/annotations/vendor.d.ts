declare module 'rbush' {
  export interface RBushBBox {
    minX: number
    minY: number
    maxX: number
    maxY: number
  }

  export default class RBush<T extends RBushBBox> {
    constructor(maxEntries?: number)
    all(): T[]
    search(bbox: RBushBBox): T[]
    insert(item: T): this
    load(items: T[]): this
    remove(item: T, equals?: (left: T, right: T) => boolean): this
    clear(): this
  }
}
