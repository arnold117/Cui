export default function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center text-zinc-500">
      <div className="text-center space-y-2">
        <p className="text-base">&larr; 从左侧选择一个想法</p>
        <p className="text-sm text-zinc-600">或点击 <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-zinc-800 text-zinc-400 text-xs font-medium">+</span> 按钮 park 一个新的</p>
      </div>
    </div>
  )
}
