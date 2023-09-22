import os
import c4d



PLUGIN_ID = 1061447



V0 = c4d.Vector()
M0 = c4d.Matrix()



def GetRotateScaleMx(mx):
    return c4d.Matrix(v1 = mx.v1, v2 = mx.v2, v3 = mx.v3)


def MixVectorsNormal(vectors):
    if len(vectors):
        return sum(vectors) / len(vectors)
    return V0

def IsNull(baseObject):
    return baseObject.IsInstanceOf(c4d.Onull)

def IsPoint(baseObject):
    return baseObject.IsInstanceOf(c4d.Opoint) \
        or baseObject.IsInstanceOf(c4d.Opolygon) \
        or baseObject.IsInstanceOf(c4d.Ospline) \
        or baseObject.IsInstanceOf(c4d.Oline)

def IsPointOrPointGen(baseObject):
    return IsPoint(baseObject) \
        or (baseObject.GetInfo() & c4d.OBJECT_POINTOBJECT == c4d.OBJECT_POINTOBJECT) \
        or (baseObject.GetInfo() & c4d.OBJECT_POLYGONOBJECT == c4d.OBJECT_POLYGONOBJECT) \
        or (baseObject.GetInfo() & c4d.OBJECT_ISSPLINE == c4d.OBJECT_ISSPLINE)


def GetKeyModifiers():
    bc = c4d.BaseContainer()
    if c4d.gui.GetInputState(c4d.BFM_INPUT_KEYBOARD, c4d.BFM_INPUT_CHANNEL, bc):
        return {
            "ctrl": bc[c4d.BFM_INPUT_QUALIFIER] & c4d.QCTRL == c4d.QCTRL,
            "alt": bc[c4d.BFM_INPUT_QUALIFIER] & c4d.QALT == c4d.QALT,
            "shift": bc[c4d.BFM_INPUT_QUALIFIER] & c4d.QSHIFT == c4d.QSHIFT,
        }

    return { "ctrl": False, "alt": False, "shift": False }


def ExecModelingTool(target, doc, commandId, settings = None, mode = c4d.MODELINGCOMMANDMODE_ALL):
    return c4d.utils.SendModelingCommand(
        command = commandId,
        list = target if isinstance(target, list) else [target],
        mode = mode,
        bc = settings or c4d.BaseContainer(),
        doc = doc
    )


def HierarchyIterator(op, includeNeigbors = False):
    while op:
        yield op
        for opChild in HierarchyIterator(op.GetDown(), True):
            yield opChild
        op = op.GetNext() if includeNeigbors else None


def HierarchyReverseIterator(op, includeNeigbors = False):
    while op:
        for opChild in HierarchyReverseIterator(op.GetDown(), True):
            yield opChild
        yield op
        op = op.GetNext() if includeNeigbors else None


def NeighborsIterator(op):
    while op:
        yield op
        op = op.GetNext()


def GetPointCache(op) :
    cacheOp = op.GetCache()
    geoOp = (cacheOp.GetDeformCache() if cacheOp else None) or op.GetDeformCache() or cacheOp or op
    return geoOp if (geoOp and IsPoint(geoOp)) else None


def DeformCacheIterator(op):
    temp = None if IsNull(op) else op.GetDeformCache()

    if temp is None:
        temp = op.GetCache()

        if temp is None:
            if not op.GetBit(c4d.BIT_CONTROLOBJECT) and op.GetDeformMode() and IsPointOrPointGen(op):
                yield op
        else:
            for obj in DeformCacheIterator(temp):
                yield obj
    else:
        for obj in DeformCacheIterator(temp):
            yield obj

    temp = op.GetDown()

    while temp:
        for obj in DeformCacheIterator(temp):
            yield obj
        temp = temp.GetNext()


def MergeContainer(temporalContainer, doc):
    joinResult = ExecModelingTool(temporalContainer, doc, c4d.MCOMMAND_JOIN)

    if not joinResult or not isinstance(joinResult, list):
        temporalContainer.Remove()
        return None

    container = c4d.BaseObject(c4d.Onull)
    for res in joinResult:
        if IsPointOrPointGen(res):
            res.InsertUnder(container)

    resCount = len(container.GetChildren())
    if resCount:
        return container.GetDown().GetClone() if resCount == 1 else container.GetClone()

    return None


def CloneAndHost(container, obj):
    cloneObject = obj.GetClone(c4d.COPYFLAGS_NO_HIERARCHY)
    cloneObject.InsertUnderLast(container)
    cloneObject.SetMg(obj.GetMg())


def GetCache(op, doc, merge = True):
    container = c4d.BaseObject(c4d.Onull)

    for cacheObject in DeformCacheIterator(op, type, True):
        CloneAndHost(container, cacheObject)

    if container.GetDown() is None:
        return None

    if len(container.GetChildren()) == 1:
        return container.GetDown().GetClone()

    return MergeContainer(
        container, doc,
    ) if merge else container


def ChildrenAxisCenter(op):
    return MixVectorsNormal([childOp.GetAbsPos() for childOp in NeighborsIterator(op)])


def CenterSimple(op, doc, toChildren):
    opMl = op.GetMl()
    opMp = ChildrenAxisCenter(op.GetDown()) if toChildren else op.GetMp()

    doc.AddUndo(c4d.UNDOTYPE_CHANGE, op)

    # shift self position to new center
    op.SetAbsPos(opMl.off + GetRotateScaleMx(opMl) * opMp)

    # shift back self points (for editable geometry)
    if IsPoint(op):
        op.SetAllPoints([(pos - opMp) for pos in op.GetAllPoints()])

    op.Message(c4d.MSG_UPDATE)

    # shift back direct children
    for opNeighbor in NeighborsIterator(op.GetDown()):
        opNeighbor.SetAbsPos(opNeighbor.GetAbsPos() - opMp)
        opNeighbor.Message(c4d.MSG_UPDATE)


def CenterDeep(op, doc, toChildren):
    for opChild in HierarchyReverseIterator(op):
        CenterSimple(opChild, doc, toChildren)


class CenterAxisData(c4d.plugins.CommandData):

    def Execute(self, doc):
        activeObjects = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)

        if len(activeObjects):
            keyMod = GetKeyModifiers()

            doc.StartUndo()

            for activeObject in activeObjects:
                (CenterDeep if keyMod["shift"] else CenterSimple)(
                    activeObject,
                    doc,
                    toChildren = keyMod["alt"],
                )

            doc.EndUndo()
            c4d.EventAdd()

        return True


if __name__ == "__main__":
    dir, file = os.path.split(__file__)
    bmp = c4d.bitmaps.BaseBitmap()
    bmp.InitWith(os.path.join(dir, "res", "icon.png"))

    c4d.plugins.RegisterCommandPlugin(
        id = PLUGIN_ID,
        str = "Center Axis",
        help = "Center Axis 0.0.1 | Click: Center to own bounds | +Shift: Deep | +Alt/Option: Center to Children axes",
        info = 0,
        icon = bmp,
        dat = CenterAxisData(),
    )
