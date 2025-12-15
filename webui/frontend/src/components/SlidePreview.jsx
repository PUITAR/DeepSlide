import React, { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

const SlidePreview = ({ slides }) => {
  const [currentSlide, setCurrentSlide] = useState(0)

  if (!slides || slides.length === 0) return null

  const nextSlide = () => {
    setCurrentSlide((prev) => (prev + 1) % slides.length)
  }

  const prevSlide = () => {
    setCurrentSlide((prev) => (prev - 1 + slides.length) % slides.length)
  }

  return (
    <div className="mt-6">
      {slides.length > 1 && (
        <div className="flex items-center justify-between px-6 py-3 border border-gray-200 dark:border-gray-800 rounded-xl bg-white dark:bg-[#171717]">
          <button
            onClick={prevSlide}
            className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            title="Previous slide"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {currentSlide + 1} / {slides.length}
            </span>
            <div className="flex gap-1.5">
              {slides.map((_, index) => (
                <button
                  key={index}
                  onClick={() => setCurrentSlide(index)}
                  className={`w-1.5 h-1.5 rounded-full transition-colors ${
                    index === currentSlide
                      ? 'bg-purple-600 dark:bg-purple-500'
                      : 'bg-gray-300 dark:bg-gray-700'
                  }`}
                  title={`Go to slide ${index + 1}`}
                />
              ))}
            </div>
          </div>

          <button
            onClick={nextSlide}
            className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            title="Next slide"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      )}
    </div>
  )
}

export default SlidePreview

